import SwiftUI

public struct ArcGauge: View {
    public enum Theme {
        case kp, bz, pfu, schumann, custom(Color)
        
        var color: Color {
            switch self {
            case .kp: return Color(red: 0.49, green: 0.77, blue: 1.0)
            case .bz: return Color(red: 1.0, green: 0.62, blue: 0.71)
            case .pfu: return Color(red: 0.97, green: 0.64, blue: 0.36)
            case .schumann: return Color(red: 0.70, green: 0.95, blue: 0.48)
            case .custom(let c): return c
            }
        }
    }
    
    public var value: Double
    public var min: Double
    public var max: Double
    public var label: String
    public var unit: String
    public var theme: Theme
    
    public init(value: Double, min: Double, max: Double, label: String, unit: String = "", theme: Theme = .kp) {
        self.value = value
        self.min = min
        self.max = max
        self.label = label
        self.unit = unit
        self.theme = theme
    }
    
    private var clamped: Double { Swift.min(Swift.max(value, min), max) }
    private var pct: Double { (clamped - min) / (max - min) }
    
    public var body: some View {
        ZStack {
            Circle()
                .trim(from: 0, to: 1)
                .stroke(Color.white.opacity(0.08), style: StrokeStyle(lineWidth: 11, lineCap: .round))
                .rotationEffect(.degrees(-90))
            
            Circle()
                .trim(from: 0, to: pct)
                .stroke(theme.color, style: StrokeStyle(lineWidth: 11, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .shadow(color: theme.color.opacity(0.6), radius: 6, x: 0, y: 0)
                .animation(.easeOut(duration: 0.6), value: pct)
            
            VStack(spacing: 4) {
                Text(value == floor(value) ? String(format: "%.0f", clamped) : String(format: "%.2f", clamped))
                    .font(.system(size: 22, weight: .heavy, design: .rounded))
                if !unit.isEmpty {
                    Text(unit)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundColor(.white.opacity(0.6))
                }
                Text(label)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundColor(.white.opacity(0.7))
            }
        }
        .padding(16)
        .background(Color.black.opacity(0.25))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

struct ArcGauge_Previews: PreviewProvider {
    static var previews: some View {
        ZStack {
            Color(red: 0.07, green: 0.09, blue: 0.14).ignoresSafeArea()
            HStack {
                ArcGauge(value: 5.3, min: 0, max: 9, label: "Kp", theme: .kp)
                ArcGauge(value: -7.8, min: -20, max: 20, label: "Bz", unit: "nT", theme: .bz)
            }.padding()
        }
        .preferredColorScheme(.dark)
    }
}
