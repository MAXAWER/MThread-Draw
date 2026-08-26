using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace MThreadDraw;

/// <summary>
/// The MThread Draw engine, running as a child process and spoken to over a pipe.
/// </summary>
/// <remarks>
/// <para>Everything interesting - tracing an image, finding a device, injecting
/// touches - lives in the Python engine, which the other platforms use too.
/// This class is the whole of the Windows side's knowledge of it: send a JSON
/// line, wait for the reply with the same id, and raise an event for anything
/// that arrives unasked.</para>
///
/// <para>The alternative was porting the engine to C#, which would mean two
/// implementations of the same subtleties, and they would drift apart by the
/// second release.</para>
/// </remarks>
public sealed class Engine : IAsyncDisposable
{
    private readonly Process _process;
    private readonly Dictionary<int, TaskCompletionSource<JsonNode>> _pending = new();
    private readonly SemaphoreSlim _writeLock = new(1, 1);
    private int _nextId;

    public event Action<string>? StatusChanged;
    public event Action<int, int>? ProgressChanged;
    public event Action<string>? Failed;
    public event Action<string, int, int>? FrameReady;
    public event Action<string>? MirrorLost;

    private Engine(Process process)
    {
        _process = process;
        _ = Task.Run(ReadLoopAsync);
    }

    /// <summary>Where the engine is, in a release and in a source checkout.</summary>
    public static (string file, string arguments) Locate()
    {
        var here = AppContext.BaseDirectory;

        // A release ships the engine as one executable beside the app.
        var packaged = Path.Combine(here, "engine", "mthread-draw-engine.exe");
        if (File.Exists(packaged))
        {
            return (packaged, string.Empty);
        }

        // A source checkout runs it from the repository's virtual environment,
        // and failing that from whatever python is on PATH.
        var repository = FindRepository();
        var venv = repository is null ? null : Path.Combine(repository, "venv", "Scripts", "python.exe");
        var python = venv is not null && File.Exists(venv) ? venv : "python";
        return (python, "-m mthread_draw.server");
    }

    /// <summary>Walk up from the binary looking for the engine's own source.</summary>
    /// <remarks>
    /// Counting "..\..\.." from the output directory works until somebody
    /// changes the configuration, the framework or the runtime identifier, at
    /// which point it silently points at the wrong folder. A marker file does
    /// not have that problem.
    /// </remarks>
    public static string? FindRepository()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "mthread_draw", "server.py")))
            {
                return directory.FullName;
            }
            directory = directory.Parent;
        }
        return null;
    }

    public static async Task<Engine> StartAsync()
    {
        var (file, arguments) = Locate();
        var repository = FindRepository();

        var info = new ProcessStartInfo(file, arguments)
        {
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            WorkingDirectory = repository ?? AppContext.BaseDirectory,
        };

        var process = Process.Start(info)
                      ?? throw new InvalidOperationException($"Could not start the engine: {file}");

        var engine = new Engine(process);
        // The engine announces itself; if that never arrives, nothing else will.
        var ready = await engine.WaitForReadyAsync().ConfigureAwait(false);
        if (!ready)
        {
            var complaint = await process.StandardError.ReadToEndAsync().ConfigureAwait(false);
            throw new InvalidOperationException(
                $"The engine did not start.\n{file} {arguments}\n{complaint}");
        }
        return engine;
    }

    private TaskCompletionSource<bool> _ready = new();

    private Task<bool> WaitForReadyAsync()
    {
        return Task.WhenAny(_ready.Task, Task.Delay(TimeSpan.FromSeconds(30)))
                   .ContinueWith(t => _ready.Task.IsCompletedSuccessfully && _ready.Task.Result);
    }

    private async Task ReadLoopAsync()
    {
        try
        {
            while (await _process.StandardOutput.ReadLineAsync().ConfigureAwait(false) is { } line)
            {
                if (line.Length == 0)
                {
                    continue;
                }

                JsonNode? message;
                try
                {
                    message = JsonNode.Parse(line);
                }
                catch (JsonException)
                {
                    continue;
                }
                if (message is null)
                {
                    continue;
                }

                if (message["event"] is { } name)
                {
                    Dispatch(name.GetValue<string>(), message);
                    continue;
                }

                var id = message["id"]?.GetValue<int>();
                if (id is not null)
                {
                    TaskCompletionSource<JsonNode>? waiting;
                    lock (_pending)
                    {
                        _pending.Remove(id.Value, out waiting);
                    }
                    waiting?.TrySetResult(message);
                }
            }
        }
        catch (Exception error)
        {
            Failed?.Invoke(error.Message);
        }
    }

    private void Dispatch(string name, JsonNode message)
    {
        switch (name)
        {
            case "ready":
                _ready.TrySetResult(true);
                break;
            case "status":
                StatusChanged?.Invoke(message["text"]?.GetValue<string>() ?? string.Empty);
                break;
            case "progress":
                ProgressChanged?.Invoke(message["done"]?.GetValue<int>() ?? 0,
                                        message["total"]?.GetValue<int>() ?? 1);
                break;
            case "frame":
                FrameReady?.Invoke(message["path"]?.GetValue<string>() ?? string.Empty,
                                   message["width"]?.GetValue<int>() ?? 0,
                                   message["height"]?.GetValue<int>() ?? 0);
                break;
            case "mirror_lost":
                MirrorLost?.Invoke(message["error"]?.GetValue<string>() ?? string.Empty);
                break;
        }
    }

    /// <summary>Send one request and wait for its reply.</summary>
    /// <exception cref="EngineException">The engine reported a problem.</exception>
    public async Task<JsonNode> CallAsync(string operation, object? arguments = null)
    {
        var id = Interlocked.Increment(ref _nextId);
        var request = new JsonObject { ["id"] = id, ["op"] = operation };
        if (arguments is not null)
        {
            foreach (var field in JsonSerializer.SerializeToNode(arguments)!.AsObject())
            {
                request[field.Key] = field.Value?.DeepClone();
            }
        }

        var waiting = new TaskCompletionSource<JsonNode>(TaskCreationOptions.RunContinuationsAsynchronously);
        lock (_pending)
        {
            _pending[id] = waiting;
        }

        await _writeLock.WaitAsync().ConfigureAwait(false);
        try
        {
            await _process.StandardInput.WriteLineAsync(request.ToJsonString()).ConfigureAwait(false);
            await _process.StandardInput.FlushAsync().ConfigureAwait(false);
        }
        finally
        {
            _writeLock.Release();
        }

        var reply = await waiting.Task.ConfigureAwait(false);
        if (reply["ok"]?.GetValue<bool>() != true)
        {
            throw new EngineException(reply["error"]?.GetValue<string>() ?? "the engine refused");
        }
        return reply["result"] ?? new JsonObject();
    }

    /// <summary>Send a request without waiting - for stop, which cannot queue.</summary>
    public async Task PostAsync(string operation)
    {
        await _writeLock.WaitAsync().ConfigureAwait(false);
        try
        {
            await _process.StandardInput.WriteLineAsync($"{{\"op\": \"{operation}\"}}").ConfigureAwait(false);
            await _process.StandardInput.FlushAsync().ConfigureAwait(false);
        }
        finally
        {
            _writeLock.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        try
        {
            await PostAsync("quit").ConfigureAwait(false);
            if (!_process.WaitForExit(3000))
            {
                _process.Kill(entireProcessTree: true);
            }
        }
        catch (Exception)
        {
            // Shutting down; a dead engine is the desired outcome either way.
        }
        _process.Dispose();
    }
}

public sealed class EngineException : Exception
{
    public EngineException(string message) : base(message)
    {
    }
}
