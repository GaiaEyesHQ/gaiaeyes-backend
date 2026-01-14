import SwiftUI
import CoreBluetooth
import UIKit

struct BleSettingsView: View {
    @ObservedObject var app: AppState
    @State private var selected: CBPeripheral?

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                Text("BLE Sensors").font(.title2).bold()
                Spacer()
                Button("Scan") { app.startBleScan() }
                Button("Stop") { app.stopBleScan() }
            }
            if let uuid = app.lastBlePeripheralUUID {
                HStack(spacing: 8) {
                    Text("Last UUID: \(uuid)")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Button("Copy") { UIPasteboard.general.string = uuid }
                        .font(.footnote)
                }
            }

            List(app.bleDevices, id: \.identifier) { p in
                HStack {
                    Text(p.name ?? "Unknown")
                    Spacer()
                    if app.bleConnected?.identifier == p.identifier {
                        Text("Connected").foregroundColor(.green)
                    }
                }
                .contentShape(Rectangle())
                .onTapGesture { selected = p }
            }

            HStack {
                Button("Connect") {
                    if let p = selected { app.connectBle(to: p) }
                }
                .disabled(selected == nil)

                Button("Disconnect") { app.disconnectBle() }

                Spacer()
                Toggle("Auto-upload RR/HR", isOn: $app.bleAutoUpload)
            }

            Divider().padding(.vertical, 4)

            GroupBox("Polar ECG") {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text("Device ID:")
                        TextField("e.g. 12345678", text: $app.polarDeviceId)
                            .textFieldStyle(.roundedBorder)
                            .textInputAutocapitalization(.never)
                            .disableAutocorrection(true)
                    }
                    Text("Use the short Polar ID (e.g. 05A2BB3A), not the CoreBluetooth UUID.")
                        .font(.caption2)
                        .foregroundColor(.secondary)

                    if let pid = app.polarConnectedId {
                        Text("Connected: \(pid)")
                            .foregroundColor(.green)
                            .font(.footnote)
                    } else {
                        Text("Not connected")
                            .foregroundColor(.secondary)
                            .font(.footnote)
                    }

                    HStack(spacing: 12) {
                        Button("Connect Polar") { app.connectPolar() }
                        Button("Disconnect Polar") { app.disconnectPolar() }
                        Spacer()
                        if app.isEcgStreaming {
                            Button("Stop ECG") { app.stopPolarEcg() }
                                .buttonStyle(.borderedProminent)
                                .tint(.red)
                        } else {
                            Button("Start ECG") { app.startPolarEcg() }
                                .buttonStyle(.borderedProminent)
                        }
                    }
                }
                .padding(.vertical, 6)
            }

            Spacer()
        }
        .padding()
        .onAppear { app.refreshBleDevices() }
    }
}//
//  BleSettingsView.swift
//  GaiaExporter
//
//  Created by Jennifer O'Brien on 9/6/25.
//

