import AppKit
import SwiftUI

/// The application, assembled by hand rather than by an Xcode template.
///
/// A Swift package builds with `swift build` on a runner with no Xcode project
/// to keep in sync, and tools/build_macos.py wraps the binary in a bundle. The
/// cost is that the window has to be created here instead of being declared,
/// which is worth it for one window.
@main
struct MThreadDrawApp {
    static func main() {
        let application = NSApplication.shared
        let delegate = Delegate()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        application.run()
    }
}

final class Delegate: NSObject, NSApplicationDelegate {
    private var window: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1040, height: 760),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false)

        window.title = "MThread Draw"
        window.makeGlassy()
        window.contentView = NSHostingView(rootView: ContentView())
        window.setFrameAutosaveName("MThreadDraw")
        window.minSize = NSSize(width: 820, height: 600)
        window.center()
        window.makeKeyAndOrderFront(nil)
        self.window = window

        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}
