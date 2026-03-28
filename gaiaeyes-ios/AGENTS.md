- Project: `ios/GaiaExporter.xcodeproj` (project path retained for stability)
- App scheme: `GaiaEyes`
- Package Manager: Swift Package Manager (SPM)
- Dependencies:
  - PolarBleSdk 6.5.0
  - RxSwift 6.5.0
  - SwiftProtobuf 1.31.0
  - Zip 2.1.2
- Build:
  `xcodebuild -scheme GaiaEyes -project ios/GaiaExporter.xcodeproj -destination 'generic/platform=iOS' -configuration Debug build`
- Tests (if present):
  `xcodebuild -scheme GaiaEyes -project ios/GaiaExporter.xcodeproj -destination 'platform=iOS Simulator,name=iPhone 15' test`
- Signing: Automatic for PR builds; releases via separate workflow.
- CI: `.github/workflows/ios-ci.yml`
