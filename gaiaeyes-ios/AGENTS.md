- Project: `ios/GaiaExporter.xcodeproj`
- Package Manager: Swift Package Manager (SPM)
- Dependencies:
  - PolarBleSdk 6.5.0
  - RxSwift 6.5.0
  - SwiftProtobuf 1.31.0
  - Zip 2.1.2
- Build:
  `xcodebuild -scheme GaiaExporter -project ios/GaiaExporter.xcodeproj -destination 'generic/platform=iOS' -configuration Debug build`
- Tests (if present):
  `xcodebuild -scheme GaiaExporterTests -project ios/GaiaExporter.xcodeproj -destination 'platform=iOS Simulator,name=iPhone 15' test`
- Signing: Automatic for PR builds; releases via separate workflow.
- CI: `.github/workflows/ios-ci.yml`
