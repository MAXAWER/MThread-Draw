import AppKit
import SwiftUI

/// The frosted material the whole window sits on.
///
/// SwiftUI has `.background(.ultraThinMaterial)`, and it is not the same thing:
/// that frosts what is behind it *inside* the window. `NSVisualEffectView` with
/// `behindWindow` blending samples the desktop and whatever is under the window,
/// which is what makes a window look like glass rather than like a grey panel.
struct Glass: NSViewRepresentable {
    var material: NSVisualEffectView.Material = .underWindowBackground

    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = material
        view.blendingMode = .behindWindow
        // Frosted whether or not the window has focus; the alternative is a
        // window that turns opaque the moment you click somewhere else.
        view.state = .active
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {
        view.material = material
    }
}

/// A card that reads as a pane of glass laid on the window's own frost.
struct GlassCard<Content: View>: View {
    var padding: CGFloat = 18
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(padding)
            .background {
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(.white.opacity(0.06))
                    .background {
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(.ultraThinMaterial)
                    }
                    .overlay {
                        // A hairline that catches the light along the top edge,
                        // which is most of what makes glass look like glass.
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .strokeBorder(
                                LinearGradient(
                                    colors: [.white.opacity(0.22), .white.opacity(0.05)],
                                    startPoint: .top, endPoint: .bottom),
                                lineWidth: 1)
                    }
            }
    }
}

extension NSWindow {
    /// Make the window itself transparent enough for the frost to show.
    func makeGlassy() {
        titleVisibility = .hidden
        titlebarAppearsTransparent = true
        isMovableByWindowBackground = true
        // The frost comes from the visual effect view; an opaque window would
        // paint over it before the view ever drew.
        isOpaque = false
        backgroundColor = .clear
        styleMask.insert(.fullSizeContentView)
    }
}
