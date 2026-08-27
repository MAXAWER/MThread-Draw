// swift-tools-version:5.9
//
// The macOS front end. A window and nothing more: tracing, ADB and touch
// injection all live in the Python engine, which Windows uses too, and which
// this launches as a child process and speaks JSON lines to over a pipe.
//
// A Swift package rather than an Xcode project on purpose - it builds with
// `swift build` on a CI runner with no Xcode project file to keep in sync, and
// tools/build_macos.py assembles the .app bundle around the binary afterwards.
import PackageDescription

let package = Package(
    name: "MThreadDraw",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "MThreadDraw",
            path: "Sources/MThreadDraw",
            swiftSettings: [.unsafeFlags(["-parse-as-library"])]
        )
    ]
)
