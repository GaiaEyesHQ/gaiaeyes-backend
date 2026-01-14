//
//  HrSession.swift
//  GaiaExporter
//
//  Created by Jennifer O'Brien on 9/6/25.
//

import Foundation
import CoreBluetooth

protocol HrSessionDelegate: AnyObject {
    func hrSessionLog(_ msg: String)
    func hrSessionDidParse(hrBpm: Int?, rrMs: [Int])
}

final class HrSession: NSObject, CBPeripheralDelegate {
    private(set) var peripheral: CBPeripheral
    private let HR_SERVICE = CBUUID(string: "180D")
    private let HR_MEAS    = CBUUID(string: "2A37")

    weak var delegate: HrSessionDelegate?

    init(peripheral: CBPeripheral) {
        self.peripheral = peripheral
        super.init()
        // Avoid silently stealing delegate from another owner (e.g., BleManager)
        if peripheral.delegate == nil || peripheral.delegate === self {
            peripheral.delegate = self
        } else {
            delegate?.hrSessionLog("⚠️ HrSession not delegate for \(peripheral.name ?? "Peripheral"); current delegate is \(String(describing: type(of: peripheral.delegate!))). Make sure BleManager forwards 2A37 updates to HrSession or releases the delegate.")
        }
        peripheral.discoverServices([HR_SERVICE])
        delegate?.hrSessionLog("Discovering Heart Rate service (180D)…")
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        if let e = error { delegate?.hrSessionLog("discoverServices error: \(e.localizedDescription)"); return }
        guard let services = peripheral.services else { return }
        if services.isEmpty {
            delegate?.hrSessionLog("No services on \(peripheral.name ?? "Peripheral")")
        }
        for s in services where s.uuid == HR_SERVICE {
            peripheral.discoverCharacteristics([HR_MEAS], for: s)
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        if let e = error { delegate?.hrSessionLog("discoverChars error: \(e.localizedDescription)"); return }
        guard let chars = service.characteristics else { return }
        for c in chars where c.uuid == HR_MEAS {
            // Only subscribe if characteristic supports notify and isn’t already notifying
            if c.properties.contains(.notify) && !c.isNotifying {
                peripheral.setNotifyValue(true, for: c)
                delegate?.hrSessionLog("Subscribing Heart Rate Measurement (2A37)…")
            } else {
                delegate?.hrSessionLog("Heart Rate Measurement (2A37) notify already active or not supported")
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error {
            delegate?.hrSessionLog("notifyState error: \(e.localizedDescription)")
            return
        }
        delegate?.hrSessionLog("notify \(characteristic.uuid) → \(characteristic.isNotifying ? "ON" : "OFF")")
    }

    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        if let e = error { delegate?.hrSessionLog("updateValue error: \(e.localizedDescription)"); return }
        guard let data = characteristic.value, characteristic.uuid == HR_MEAS else { return }
        parseHrMeasurement(data)
    }

    /// Forwarder for parsed Heart Rate values (e.g., from BleManager). RR intervals are in seconds.
    /// Converts RR seconds to milliseconds and routes through the existing delegate.
    @MainActor
    func ingestHR(bpm: Int?, rrSec: [Double]?) {
        let rrMs = (rrSec ?? []).map { Int(($0 * 1000.0).rounded()) }
        delegate?.hrSessionDidParse(hrBpm: bpm, rrMs: rrMs)
    }

    // BLE Heart Rate Measurement parser (GATT spec)
    private func parseHrMeasurement(_ data: Data) {
        var idx = 0
        guard data.count >= 2 else { return }
        let flags = data[idx]; idx += 1
        let hr16         = (flags & 0x01) != 0
        let energyPresent = (flags & 0x08) != 0
        let rrPresent     = (flags & 0x10) != 0

        var hr: Int?
        if hr16 {
            guard idx + 2 <= data.count else { return }
            hr = Int(UInt16(data[idx]) | (UInt16(data[idx+1]) << 8))
            idx += 2
        } else {
            guard idx + 1 <= data.count else { return }
            hr = Int(data[idx])
            idx += 1
        }

        // Skip Energy Expended field if present (2 bytes)
        if energyPresent, idx + 2 <= data.count { idx += 2 }

        var rr: [Int] = []
        if rrPresent {
            while idx + 1 < data.count {
                let rrRaw = UInt16(data[idx]) | (UInt16(data[idx+1]) << 8)
                // RR in 1/1024 seconds per GATT spec, convert to ms
                let rrMs = Int((Double(rrRaw) / 1024.0) * 1000.0)
                rr.append(rrMs)
                idx += 2
            }
        }
        delegate?.hrSessionDidParse(hrBpm: hr, rrMs: rr)
    }
}
