import SwiftUI

public struct StatusPill: View {
    public enum Severity { case ok, warn, alert }
    public var text: String
    public var severity: Severity
    
    public init(_ text: String, severity: Severity) {
        self.text = text
        self.severity = severity
    }
    
    public var body: some View {
        Text(text.uppercased())
            .font(.system(size: 12, weight: .heavy, design: .rounded))
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(backgroundColor)
            .foregroundColor(foregroundColor)
            .overlay(RoundedRectangle(cornerRadius: 999).stroke(Color.white.opacity(0.12), lineWidth: 1))
            .clipShape(Capsule())
            .shadow(color: severity == .alert ? Color.red.opacity(0.5) : .clear, radius: 8, x: 0, y: 0)
    }
    
    private var backgroundColor: Color {
        switch severity {
        case .ok: return Color(red: 0.23, green: 0.43, blue: 0.33)
        case .warn: return Color(red: 0.51, green: 0.40, blue: 0.14)
        case .alert: return Color(red: 0.48, green: 0.19, blue: 0.19)
        }
    }
    private var foregroundColor: Color {
        switch severity {
        case .ok: return Color(red: 0.84, green: 1.0, blue: 0.92)
        case .warn: return Color(red: 1.0, green: 0.90, blue: 0.68)
        case .alert: return Color(red: 1.0, green: 0.78, blue: 0.78)
        }
    }
}

struct StatusPill_Previews: PreviewProvider {
    static var previews: some View {
        HStack {
            StatusPill("OK", severity: .ok)
            StatusPill("WARN", severity: .warn)
            StatusPill("ALERT", severity: .alert)
        }.padding()
        .background(Color.black.opacity(0.9))
        .preferredColorScheme(.dark)
    }
}
