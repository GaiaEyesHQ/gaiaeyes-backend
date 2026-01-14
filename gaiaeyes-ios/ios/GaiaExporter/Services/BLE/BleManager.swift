import Foundation
import CoreBluetooth

protocol BleManagerDelegate: AnyObject {
    func bleManagerDidUpdateDevices(_ devices: [CBPeripheral])
    func bleManagerDidConnect(_ peripheral: CBPeripheral)
    func bleManagerDidDisconnect(_ peripheral: CBPeripheral, error: Error?)
    func bleManagerLog(_ msg: String)
    /// Forward parsed Heart Rate Measurement (GATT 2A37). `rr` contains RR intervals in seconds if present.
    func bleManagerDidReceiveHeartRate(_ bpm: Int, rr: [Double]?, from peripheral: CBPeripheral)
}

final class BleManager: NSObject, ObservableObject {
    enum State { case idle, scanning, connecting, connected }
    @Published private(set) var state: State = .idle
    @Published private(set) var devices: [CBPeripheral] = []

    private let central: CBCentralManager
    private var discovered: [UUID: CBPeripheral] = [:]
    private var autoConnectUUID: UUID?
    private var ecgMode: Bool = false
    // Dual‑phase scan control
    private var isScanning = false
    private var fallbackScanWork: DispatchWorkItem?
    private var connectTarget: CBPeripheral?
    weak var delegate: BleManagerDelegate?

    // Heart Rate Service & Measurement
    private let HR_SERVICE = CBUUID(string: "180D")
    private let HR_MEAS    = CBUUID(string: "2A37")

    // Heart Rate Measurement characteristic handle
    private var hrCharacteristic: CBCharacteristic?

    override init() {
        self.central = CBCentralManager(delegate: nil, queue: .main)
        super.init()
        self.central.delegate = self
    }

    func startScan(ecgOnly: Bool = false) {
        guard central.state == .poweredOn else {
            delegate?.bleManagerLog("Bluetooth not powered on (state=\(central.state.rawValue))")
            return
        }
        // cancel any prior scan/timer
        stopScan()
        isScanning = true
        devices.removeAll()
        discovered.removeAll()
        state = .scanning
        ecgMode = ecgOnly

        if ecgOnly {
            // Scan broadly immediately for ECG devices
            delegate?.bleManagerLog("Scanning broadly for ECG devices…")
            central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
        } else {
            // Phase 1: scan with Heart Rate service filter
            delegate?.bleManagerLog("Scanning for HRM devices… (phase 1)")
            central.scanForPeripherals(withServices: [HR_SERVICE], options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])

            // If nothing shows within ~6s, broaden the scan to all services
            let work = DispatchWorkItem { [weak self] in
                guard let self = self, self.isScanning, self.devices.isEmpty else { return }
                self.delegate?.bleManagerLog("No devices yet; broadening scan (phase 2)")
                self.central.stopScan()
                self.central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
            }
            fallbackScanWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 6.0, execute: work)
        }
    }

    func stopScan() {
        isScanning = false
        state = .idle
        central.stopScan()
        fallbackScanWork?.cancel()
        fallbackScanWork = nil
    }

    func connect(to peripheral: CBPeripheral) {
        state = .connecting
        connectTarget = peripheral
        delegate?.bleManagerLog("Connecting to \(peripheral.name ?? "Unknown")")
        central.stopScan()
        central.connect(peripheral, options: nil)
        peripheral.delegate = self
    }

    func disconnect() {
        if let p = connectTarget {
            central.cancelPeripheralConnection(p)
        }
        connectTarget = nil
        hrCharacteristic = nil
    }

    /// Attempt to connect to a previously known peripheral by UUID.
    /// Tries CoreBluetooth retrieval first; if not found, starts a scan and connects on discovery.
    func connectToKnown(uuid: UUID, ecgOnly: Bool = false) {
        autoConnectUUID = uuid
        ecgMode = ecgOnly
        let known = central.retrievePeripherals(withIdentifiers: [uuid])
        if let p = known.first {
            discovered[uuid] = p
            delegate?.bleManagerLog("Found known peripheral; connecting…")
            connect(to: p)
        } else {
            delegate?.bleManagerLog("Known peripheral not immediately available; scanning…")
            startScan(ecgOnly: ecgOnly)
        }
    }
}

extension BleManager: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        delegate?.bleManagerLog("Central state: \(central.state.rawValue)")
        if central.state == .poweredOn, state == .scanning {
            startScan(ecgOnly: ecgMode)
        }
    }

    func centralManager(_ central: CBCentralManager,
                        didDiscover peripheral: CBPeripheral,
                        advertisementData: [String : Any],
                        rssi RSSI: NSNumber) {
        // Heuristic filter so phase‑2 broad scans don’t flood the UI with non‑HR devices.
        let svcUUIDs = (advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID]) ?? []
        let localName = (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? (peripheral.name ?? "")
        let lname = localName.lowercased()
        var include = false
        if ecgMode {
            // For ECG mode, only show likely Polar/HR devices by name
            include = lname.contains("polar") || lname.contains("h10") || lname.contains("heart") || lname.contains("ecg")
        } else {
            // For HR mode, include if advertising the Heart Rate service or name matches
            include = svcUUIDs.contains(HR_SERVICE) || lname.contains("polar") || lname.contains("h10") || lname.contains("heart")
        }
        guard include else { return }

        discovered[peripheral.identifier] = peripheral
        devices = Array(discovered.values).sorted { ($0.name ?? "") < ($1.name ?? "") }
        delegate?.bleManagerDidUpdateDevices(devices)

        // Auto‑connect if this is our target UUID
        if let target = autoConnectUUID, peripheral.identifier == target {
            delegate?.bleManagerLog("Auto‑connect match; connecting…")
            autoConnectUUID = nil
            connect(to: peripheral)
        }
    }
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        state = .connected
        delegate?.bleManagerLog("Connected to \(peripheral.name ?? "Unknown"); discovering Heart Rate service…")
        peripheral.delegate = self
        peripheral.discoverServices([HR_SERVICE])
        delegate?.bleManagerDidConnect(peripheral)
    }

    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        state = .idle
        delegate?.bleManagerLog("Failed to connect: \(error?.localizedDescription ?? "unknown")")
    }

    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        state = .idle
        delegate?.bleManagerDidDisconnect(peripheral, error: error)
        hrCharacteristic = nil
        // Auto-reconnect disabled by request; manage reconnection via UI/Polar preflight
        delegate?.bleManagerLog("Disconnected from target; auto-reconnect is disabled.")
    }
}

extension BleManager: CBPeripheralDelegate {
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let error = error {
            delegate?.bleManagerLog("Service discovery error: \(error.localizedDescription)")
            return
        }
        guard let services = peripheral.services, !services.isEmpty else {
            delegate?.bleManagerLog("No GATT services found on \(peripheral.name ?? "Unknown")")
            return
        }
        for svc in services {
            if svc.uuid == HR_SERVICE {
                delegate?.bleManagerLog("Found Heart Rate service; discovering measurement characteristic…")
                peripheral.discoverCharacteristics([HR_MEAS], for: svc)
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let error = error {
            delegate?.bleManagerLog("Characteristic discovery error: \(error.localizedDescription)")
            return
        }
        guard let chars = service.characteristics else { return }
        for ch in chars where ch.uuid == HR_MEAS {
            hrCharacteristic = ch
            delegate?.bleManagerLog("Subscribing to Heart Rate Measurement notifications…")
            peripheral.setNotifyValue(true, for: ch)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        if let error = error {
            delegate?.bleManagerLog("Notify state error for \(characteristic.uuid): \(error.localizedDescription)")
            return
        }
        delegate?.bleManagerLog("Notify \(characteristic.uuid) is now \(characteristic.isNotifying ? "ON" : "OFF")")
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        if let error = error {
            delegate?.bleManagerLog("Value update error: \(error.localizedDescription)")
            return
        }
        guard characteristic.uuid == HR_MEAS, let data = characteristic.value else { return }
        if let parsed = parseHeartRateMeasurement(data) {
            let rrText = parsed.rr.isEmpty ? "" : " RR: \(parsed.rr.map { String(format: "%.3fs", $0) }.joined(separator: ","))"
            delegate?.bleManagerLog("HR: \(parsed.hr) bpm\(rrText)")
            // Forward parsed measurement to the app/session layer
            delegate?.bleManagerDidReceiveHeartRate(parsed.hr, rr: parsed.rr.isEmpty ? nil : parsed.rr, from: peripheral)
        }
    }

    /// Parse BLE Heart Rate Measurement (2A37) per spec; returns heart rate (bpm) and RR intervals (s).
    private func parseHeartRateMeasurement(_ data: Data) -> (hr: Int, rr: [Double])? {
        // Byte 0: flags
        // bit0: 0=HR 8-bit, 1=HR 16-bit
        // bit4: RR-Interval present
        guard data.count >= 2 else { return nil }
        let flags = data[0]
        let hr16 = (flags & 0x01) != 0
        var idx = 1

        var hr: Int = 0
        if hr16 {
            guard data.count >= idx+2 else { return nil }
            hr = Int(UInt16(data[idx]) | (UInt16(data[idx+1]) << 8))
            idx += 2
        } else {
            hr = Int(data[idx])
            idx += 1
        }

        // Skip sensor contact, energy expended fields if present
        // bit1-2: sensor contact status, bit3: energy expended status
        let energyPresent = (flags & 0x08) != 0
        if energyPresent {
            // 2 bytes energy
            if data.count >= idx+2 { idx += 2 }
        }

        var rrs: [Double] = []
        let rrPresent = (flags & 0x10) != 0
        if rrPresent && data.count > idx {
            while data.count >= idx+2 {
                let rrRaw = UInt16(data[idx]) | (UInt16(data[idx+1]) << 8)
                // RR in 1/1024 seconds per spec
                let rrSec = Double(rrRaw) / 1024.0
                rrs.append(rrSec)
                idx += 2
            }
        }
        return (hr: hr, rr: rrs)
    }
}

//
//  BleManager.swift
//  GaiaExporter
//
//  Created by Jennifer O'Brien on 9/6/25.
//

