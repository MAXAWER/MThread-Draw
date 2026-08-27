import AppKit
import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class Model: ObservableObject {
    let engine = Engine()

    @Published var devices: [(serial: String, description: String, ready: Bool)] = []
    @Published var selected: String?
    @Published var connected = false
    @Published var deviceLabel = "Not connected"
    @Published var status = "Starting the engine…"

    @Published var layers: [(name: String, strokes: Int, erased: Int, visible: Bool)] = []
    @Published var current = 0
    @Published var totalStrokes = 0
    @Published var totalPoints = 0

    @Published var frame: NSImage?
    @Published var overlay: NSImage?
    @Published var screen = CGSize(width: 1080, height: 2280)

    @Published var detail = 7.0
    @Published var feel = 0.0
    @Published var tracer = "canny"
    @Published var estimate = ""
    @Published var progress = 0.0
    @Published var drawing = false
    @Published var erasing = false

    /// 0 draws as fast as it goes; 10 draws the way a hand would.
    var speed: Double { 8.0 * pow(0.075, feel / 10.0) }
    var human: Double { max(0, (feel - 4.0) / 3.0) }

    var hasImage: Bool { !layers.isEmpty }

    func begin() async {
        engine.onStatus = { [weak self] text in Task { @MainActor in self?.status = text } }
        engine.onProgress = { [weak self] done, total in
            Task { @MainActor in self?.progress = total > 0 ? Double(done) / Double(total) : 0 }
        }
        engine.onFrame = { [weak self] path, width, height in
            Task { @MainActor in self?.showFrame(path, width, height) }
        }
        engine.onMirrorLost = { [weak self] reason in
            Task { @MainActor in self?.status = "The live view stopped: \(reason)" }
        }

        do {
            try await engine.start()
            status = "Ready."
            await refreshDevices()
        } catch {
            status = error.localizedDescription
        }
    }

    func refreshDevices() async {
        do {
            let result = try await engine.call("devices")
            let list = result["devices"] as? [[String: Any]] ?? []
            devices = list.map {
                ($0["serial"] as? String ?? "?",
                 $0["description"] as? String ?? "",
                 ($0["state"] as? String) == "device")
            }
            selected = devices.first?.serial

            if devices.count == 1, devices[0].ready, !connected {
                // One device is not a choice, and the live view is the reason
                // the window is worth looking at.
                await connect()
            } else if devices.isEmpty {
                status = "No device, and restarting adb did not find one. "
                       + "Check the cable, turn on USB debugging, and accept the prompt on the phone."
            } else {
                status = "\(devices.count) device(s) found."
            }
        } catch {
            status = error.localizedDescription
        }
    }

    func connect() async {
        do {
            var arguments: [String: Any] = [:]
            if let selected { arguments["serial"] = selected }
            let result = try await engine.call("connect", arguments)

            let width = result["width"] as? Int ?? 1080
            let height = result["height"] as? Int ?? 2280
            screen = CGSize(width: width, height: height)
            connected = true
            deviceLabel = "\(result["serial"] as? String ?? "?") · \(width)×\(height)"
            status = (result["raw_touch"] as? Bool ?? false)
                ? "Connected. This device allows raw touch events, which is the fast path."
                : "Connected. This device refuses raw touch events, so drawing goes through the injector."

            _ = try await engine.call("mirror", ["on": true])
            await refreshEstimate()
        } catch {
            status = error.localizedDescription
        }
    }

    private func showFrame(_ path: String, _ width: Int, _ height: Int) {
        if width > 0, height > 0 {
            screen = CGSize(width: width, height: height)
        }
        // Read the bytes rather than pointing an image at the file: the engine
        // is writing the next frame while this one is on screen.
        guard let data = FileManager.default.contents(atPath: path) else { return }
        frame = NSImage(data: data)
    }

    private func apply(_ result: [String: Any]) {
        let list = result["layers"] as? [[String: Any]] ?? []
        layers = list.map {
            ($0["name"] as? String ?? "?",
             $0["strokes"] as? Int ?? 0,
             $0["erased"] as? Int ?? 0,
             $0["visible"] as? Bool ?? true)
        }
        current = result["current"] as? Int ?? 0
        totalStrokes = result["strokes"] as? Int ?? 0
        totalPoints = result["points"] as? Int ?? 0
        if let path = result["overlay"] as? String,
           let data = FileManager.default.contents(atPath: path) {
            overlay = NSImage(data: data)
        } else if layers.isEmpty {
            overlay = nil
        }
    }

    func run(_ operation: String, _ arguments: [String: Any] = [:]) async {
        do {
            apply(try await engine.call(operation, arguments))
            await refreshEstimate()
        } catch {
            status = error.localizedDescription
        }
    }

    func loadImage() async {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.png, .jpeg, .bmp, .webP]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        await run("load_image", ["path": url.path])
    }

    func preview() async {
        await run("preview", ["sensitivity": detail, "detail": detail, "method": tracer])
    }

    func refreshEstimate() async {
        guard connected, hasImage else { return }
        do {
            let result = try await engine.call("estimate", ["speed": speed, "human": human])
            let seconds = result["seconds"] as? Double ?? 0
            estimate = seconds >= 60
                ? String(format: "About %d min %d s to draw.", Int(seconds) / 60, Int(seconds) % 60)
                : String(format: "About %.0f s to draw.", seconds)
        } catch {
            estimate = ""
        }
    }

    func draw() async {
        drawing = true
        defer { drawing = false; progress = 0 }
        do {
            let result = try await engine.call("draw", ["speed": speed, "human": human])
            status = (result["stopped"] as? Bool ?? false)
                ? "Stopped."
                : "Finished. \(result["strokes"] as? Int ?? 0) strokes drawn."
        } catch {
            status = error.localizedDescription
        }
    }

    func stop() { engine.post("stop") }
}

struct ContentView: View {
    @StateObject private var model = Model()

    var body: some View {
        HStack(spacing: 0) {
            controls
                .frame(width: 320)
            Divider().opacity(0.25)
            phone
                .frame(minWidth: 420)
        }
        .background(Glass())
        .safeAreaInset(edge: .bottom) { statusBar }
        .task { await model.begin() }
    }

    // MARK: - the left column

    private var controls: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                deviceRow

                GlassCard {
                    VStack(alignment: .leading, spacing: 10) {
                        Button("Load image…") { Task { await model.loadImage() } }
                            .frame(maxWidth: .infinity)
                        Text(model.hasImage
                             ? "\(model.layers.count) layer(s) · \(model.totalStrokes) strokes, \(model.totalPoints) points"
                             : "No image loaded")
                            .font(.caption).foregroundStyle(.secondary)

                        if model.hasImage { layerList }
                    }
                }

                GlassCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("What is in the picture").font(.headline)
                        Picker("", selection: $model.tracer) {
                            Text("Buildings, machines, objects").tag("canny")
                            Text("Portraits, animals, nature").tag("flow")
                        }
                        .labelsHidden()
                        .onChange(of: model.tracer) { Task { await model.preview() } }

                        slider("How much detail", value: $model.detail, range: 1...10,
                               caption: detailWord(model.detail)) {
                            Task { await model.preview() }
                        }
                        slider("How it draws", value: $model.feel, range: 0...10,
                               caption: feelWord(model.feel)) {
                            Task { await model.refreshEstimate() }
                        }

                        if !model.estimate.isEmpty {
                            Text(model.estimate).font(.callout).foregroundStyle(.secondary)
                        }
                    }
                }

                Button("START DRAWING") { Task { await model.draw() } }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .frame(maxWidth: .infinity)
                    .disabled(!model.connected || !model.hasImage || model.drawing)

                Button("Stop") { model.stop() }
                    .frame(maxWidth: .infinity)
                    .disabled(!model.drawing)
            }
            .padding(18)
        }
    }

    private var deviceRow: some View {
        GlassCard(padding: 14) {
            VStack(alignment: .leading, spacing: 8) {
                Picker("", selection: Binding(
                    get: { model.selected ?? "" },
                    set: { model.selected = $0 })) {
                    if model.devices.isEmpty {
                        Text("Looking for a device…").tag("")
                    }
                    ForEach(model.devices, id: \.serial) { device in
                        Text("\(device.serial) — \(device.description)").tag(device.serial)
                    }
                }
                .labelsHidden()

                HStack {
                    Button("Refresh") { Task { await model.refreshDevices() } }
                    Button("Connect") { Task { await model.connect() } }
                        .buttonStyle(.borderedProminent)
                }
                Text(model.deviceLabel).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var layerList: some View {
        VStack(spacing: 6) {
            ForEach(Array(model.layers.enumerated()), id: \.offset) { index, layer in
                HStack {
                    Text(layer.name).lineLimit(1)
                    Spacer()
                    Text("\(layer.strokes)").foregroundStyle(.secondary).font(.caption)
                }
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(index == model.current ? .white.opacity(0.14) : .clear)
                }
                .opacity(layer.visible ? 1 : 0.45)
                .onTapGesture { Task { await model.run("layer_select", ["index": index]) } }
            }

            HStack(spacing: 6) {
                Button("Forward") { Task { await model.run("layer_raise") } }
                Button(model.layers.indices.contains(model.current)
                       && model.layers[model.current].visible ? "Hide" : "Show") {
                    let visible = model.layers.indices.contains(model.current)
                        ? model.layers[model.current].visible : true
                    Task { await model.run("layer_visible", ["visible": !visible]) }
                }
                Button("Remove") { Task { await model.run("layer_remove") } }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
    }

    private func slider(_ title: String, value: Binding<Double>,
                        range: ClosedRange<Double>, caption: String,
                        onChange: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
            Slider(value: value, in: range, step: 1) { editing in
                if !editing { onChange() }
            }
            Text(caption).font(.caption).foregroundStyle(.secondary)
        }
    }

    // MARK: - the phone

    private var phone: some View {
        VStack(spacing: 12) {
            GeometryReader { room in
                let side = fit(in: room.size)
                ZStack {
                    RoundedRectangle(cornerRadius: 30, style: .continuous)
                        .fill(.black.opacity(0.55))
                    if let frame = model.frame {
                        Image(nsImage: frame)
                            .resizable()
                            .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                            .padding(9)
                    }
                    if let overlay = model.overlay {
                        Image(nsImage: overlay)
                            .resizable()
                            .padding(9)
                    }
                    if model.frame == nil && model.overlay == nil {
                        Text("Connect a device to see its screen here.")
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(width: side.width, height: side.height)
                .position(x: room.size.width / 2, y: room.size.height / 2)
                .gesture(placement(side: side))
            }

            HStack(spacing: 8) {
                Toggle("Erase", isOn: $model.erasing).toggleStyle(.button)
                Button("Undo erase") { Task { await model.run("erase", ["undo": true]) } }
                Button("Flip ↔") { Task { await model.run("place", ["flip_x": true]) } }
                Button("Flip ↕") { Task { await model.run("place", ["flip_y": true]) } }
                Button("Fit") { Task { await model.run("place", ["reset": true]) } }
            }
            .controlSize(.small)
            .disabled(!model.hasImage)

            Text(model.erasing
                 ? "Drag across strokes to take them out"
                 : "Drag to move it · scroll to resize · Shift and scroll to turn")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(18)
    }

    /// The phone drawn at the proportions of the real screen.
    private func fit(in room: CGSize) -> CGSize {
        let ratio = model.screen.width / max(model.screen.height, 1)
        let byHeight = CGSize(width: (room.height - 20) * ratio, height: room.height - 20)
        if byHeight.width <= room.width - 20 { return byHeight }
        return CGSize(width: room.width - 20, height: (room.width - 20) / ratio)
    }

    private func placement(side: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .onChanged { value in
                guard model.hasImage, !model.drawing else { return }
                if model.erasing {
                    let x = value.location.x / side.width
                    let y = value.location.y / side.height
                    guard (0...1).contains(x), (0...1).contains(y) else { return }
                    Task { await model.run("erase", ["x": x, "y": y, "radius": 0.025]) }
                } else {
                    // In fractions of the phone's own picture, so a drag moves
                    // the drawing the same share of the screen at any size.
                    let dx = value.translation.width / side.width
                    let dy = value.translation.height / side.height
                    Task { await model.run("place", ["dx": dx, "dy": dy]) }
                }
            }
    }

    private var statusBar: some View {
        HStack {
            Text(model.status).lineLimit(2)
            Spacer()
            if model.drawing {
                ProgressView(value: model.progress).frame(width: 180)
            }
        }
        .font(.callout)
        .padding(.horizontal, 18).padding(.vertical, 10)
        .background(.ultraThinMaterial)
    }

    private func detailWord(_ value: Double) -> String {
        switch value {
        case ..<3: return "\(Int(value)) — the shape and little else"
        case ..<5: return "\(Int(value)) — the main lines"
        case ..<7: return "\(Int(value)) — a moderate amount"
        case ..<9: return "\(Int(value)) — a fair amount"
        default: return "\(Int(value)) — everything it can find"
        }
    }

    private func feelWord(_ value: Double) -> String {
        switch value {
        case 0: return "instantly"
        case ..<3: return String(format: "very fast — %.1fx", model.speed)
        case ..<5: return String(format: "fast — %.1fx", model.speed)
        case ..<7: return String(format: "like a quick hand — %.1fx", model.speed)
        case ..<9: return String(format: "like a hand — %.1fx", model.speed)
        default: return String(format: "like a careful hand — %.1fx", model.speed)
        }
    }
}
