import Foundation

/// The MThread Draw engine, running as a child process and spoken to over a pipe.
///
/// Everything interesting - tracing an image, finding a device, injecting
/// touches - lives in the Python engine, which the Windows front end uses too.
/// This class is the whole of the Mac side's knowledge of it: write a JSON line,
/// wait for the reply carrying the same id, and publish anything that arrives
/// unasked.
///
/// Porting the engine to Swift would mean a second implementation of the same
/// subtleties, and they would drift apart by the second release.
final class Engine {

    enum EngineError: LocalizedError {
        case notStarted(String)
        case refused(String)

        var errorDescription: String? {
            switch self {
            case .notStarted(let detail): return "The engine did not start.\n\(detail)"
            case .refused(let detail): return detail
            }
        }
    }

    private let process = Process()
    private let input = Pipe()
    private let output = Pipe()
    private var nextId = 0
    private var pending: [Int: CheckedContinuation<[String: Any], Error>] = [:]
    private let lock = NSLock()
    private var buffer = Data()

    /// Called for events - anything the engine sends without being asked.
    var onStatus: ((String) -> Void)?
    var onProgress: ((Int, Int) -> Void)?
    var onFrame: ((String, Int, Int) -> Void)?
    var onMirrorLost: ((String) -> Void)?

    private var readyContinuation: CheckedContinuation<Void, Error>?

    /// Where the engine is, in a release and in a source checkout.
    static func locate() -> (URL, [String]) {
        let bundle = Bundle.main.bundleURL

        // A release ships the engine inside the bundle, beside the binary.
        let packaged = bundle
            .appendingPathComponent("Contents/Resources/engine/mthread-draw-engine")
        if FileManager.default.isExecutableFile(atPath: packaged.path) {
            return (packaged, [])
        }

        // A source checkout runs it from the repository's virtual environment,
        // and failing that from whatever python is on PATH.
        if let repository = findRepository() {
            let venv = repository.appendingPathComponent("venv/bin/python")
            let python = FileManager.default.isExecutableFile(atPath: venv.path)
                ? venv
                : URL(fileURLWithPath: "/usr/bin/env")
            let arguments = python.lastPathComponent == "env"
                ? ["python3", "-m", "mthread_draw.server"]
                : ["-m", "mthread_draw.server"]
            return (python, arguments)
        }
        return (URL(fileURLWithPath: "/usr/bin/env"),
                ["python3", "-m", "mthread_draw.server"])
    }

    /// Walk up from the binary looking for the engine's own source.
    ///
    /// Counting "../.." from the build directory works until somebody changes
    /// the configuration, at which point it silently points at the wrong folder.
    /// A marker file does not have that problem.
    static func findRepository() -> URL? {
        var directory = Bundle.main.bundleURL
        for _ in 0..<8 {
            let marker = directory.appendingPathComponent("mthread_draw/server.py")
            if FileManager.default.fileExists(atPath: marker.path) {
                return directory
            }
            directory = directory.deletingLastPathComponent()
        }
        return nil
    }

    func start() async throws {
        let (executable, arguments) = Engine.locate()
        process.executableURL = executable
        process.arguments = arguments
        process.standardInput = input
        process.standardOutput = output
        process.standardError = Pipe()
        if let repository = Engine.findRepository() {
            process.currentDirectoryURL = repository
        }

        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            self?.absorb(handle.availableData)
        }

        try process.run()

        // The engine announces itself; if that never arrives, nothing else will.
        try await withThrowingTaskGroup(of: Void.self) { group in
            group.addTask { [weak self] in
                try await withCheckedThrowingContinuation { continuation in
                    self?.readyContinuation = continuation
                }
            }
            group.addTask {
                try await Task.sleep(for: .seconds(30))
                throw EngineError.notStarted("It produced no output in thirty seconds.")
            }
            try await group.next()
            group.cancelAll()
        }
    }

    // MARK: - reading

    private func absorb(_ data: Data) {
        guard !data.isEmpty else { return }
        buffer.append(data)
        while let newline = buffer.firstIndex(of: 0x0A) {
            let line = buffer[buffer.startIndex..<newline]
            buffer = buffer[buffer.index(after: newline)...]
            handle(line: Data(line))
        }
    }

    private func handle(line: Data) {
        guard !line.isEmpty,
              let message = try? JSONSerialization.jsonObject(with: line) as? [String: Any]
        else { return }

        if let name = message["event"] as? String {
            dispatch(event: name, message: message)
            return
        }

        guard let id = message["id"] as? Int else { return }
        lock.lock()
        let waiting = pending.removeValue(forKey: id)
        lock.unlock()

        guard let waiting else { return }
        if message["ok"] as? Bool == true {
            waiting.resume(returning: message["result"] as? [String: Any] ?? [:])
        } else {
            waiting.resume(throwing: EngineError.refused(
                message["error"] as? String ?? "the engine refused"))
        }
    }

    private func dispatch(event name: String, message: [String: Any]) {
        switch name {
        case "ready":
            let continuation = readyContinuation
            readyContinuation = nil
            continuation?.resume()
        case "status":
            onStatus?(message["text"] as? String ?? "")
        case "progress":
            onProgress?(message["done"] as? Int ?? 0, message["total"] as? Int ?? 1)
        case "frame":
            onFrame?(message["path"] as? String ?? "",
                     message["width"] as? Int ?? 0,
                     message["height"] as? Int ?? 0)
        case "mirror_lost":
            onMirrorLost?(message["error"] as? String ?? "")
        default:
            break
        }
    }

    // MARK: - writing

    /// Send one request and wait for its reply.
    @discardableResult
    func call(_ operation: String, _ arguments: [String: Any] = [:]) async throws -> [String: Any] {
        lock.lock()
        nextId += 1
        let id = nextId
        lock.unlock()

        var request: [String: Any] = arguments
        request["id"] = id
        request["op"] = operation
        let line = try JSONSerialization.data(withJSONObject: request) + Data([0x0A])

        return try await withCheckedThrowingContinuation { continuation in
            lock.lock()
            pending[id] = continuation
            lock.unlock()
            input.fileHandleForWriting.write(line)
        }
    }

    /// Send a request without waiting - for stop, which cannot queue.
    func post(_ operation: String) {
        let line = "{\"op\": \"\(operation)\"}\n"
        input.fileHandleForWriting.write(Data(line.utf8))
    }

    func shutDown() {
        post("quit")
        // A dead engine is the desired outcome either way.
        DispatchQueue.global().asyncAfter(deadline: .now() + 3) { [process] in
            if process.isRunning { process.terminate() }
        }
    }
}
