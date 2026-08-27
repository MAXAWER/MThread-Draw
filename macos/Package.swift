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
        // No file here is called main.swift, which is what lets @main in
        // MThreadDrawApp.swift stand: a file by that name is top-level code,
        // and the two cannot coexist.
        .executableTarget(
            name: "MThreadDraw",
            path: "Sources/MThreadDraw"
        )
    ]
)
