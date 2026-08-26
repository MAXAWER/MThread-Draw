using System.Runtime.InteropServices.WindowsRuntime;
using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Pickers;

namespace MThreadDraw;

public sealed partial class MainWindow : Window
{
    private Engine? _engine;
    private bool _imageLoaded;
    private bool _connected;
    private bool _drawing;

    /// <summary>The margin left around a drawing, as a fraction of the screen.</summary>
    /// <remarks>
    /// This used to be a slider. It was the least interesting control in the
    /// window and it was in the way of the two that matter.
    /// </remarks>
    private const double Margin = 0.06;

    /// <summary>Coalesces slider movements: previewing on every tick would queue
    /// up seconds of work nobody is waiting for any more.</summary>
    private readonly DispatcherTimer _previewDelay = new() { Interval = TimeSpan.FromMilliseconds(350) };

    public MainWindow()
    {
        InitializeComponent();

        // Draw into the caption instead of sitting under it. The system bar
        // contributed a grey strip, a second copy of the window's name and
        // nothing else; the caption buttons stay where Windows puts them.
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        // The window does not know its DPI until it has been shown, and asking
        // sooner gets 96 and a window a third too small on a scaled display.
        var sized = false;
        Activated += (_, _) =>
        {
            if (!sized)
            {
                sized = true;
                ResizeToDips(1180, 860);
            }
        };

        _previewDelay.Tick += async (_, _) =>
        {
            _previewDelay.Stop();
            await RefreshPreviewAsync();
        };

        Closed += async (_, _) =>
        {
            if (_engine is not null)
            {
                await _engine.DisposeAsync();
            }
        };

        _ = StartEngineAsync();
    }

    private async Task StartEngineAsync()
    {
        try
        {
            _engine = await Engine.StartAsync();
            _engine.StatusChanged += text => Dispatch(() => StatusText.Text = text);
            _engine.Failed += text => Dispatch(() => StatusText.Text = text);
            _engine.ProgressChanged += (done, total) => Dispatch(() =>
                Progress.Value = total > 0 ? 100.0 * done / total : 0);
            _engine.FrameReady += (path, width, height) =>
                Dispatch(() => ShowFrame(path, width, height));
            _engine.MirrorLost += text => Dispatch(() =>
                StatusText.Text = $"The live view stopped: {text}");

            StatusText.Text = "Ready.";
            await RefreshDevicesAsync();
            await OpenFromCommandLineAsync();
        }
        catch (Exception error)
        {
            StatusText.Text = error.Message;
        }
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint GetDpiForWindow(IntPtr window);

    /// <summary>Size the window in the units the layout was written in.</summary>
    /// <remarks>
    /// AppWindow.Resize takes physical pixels, while every measurement in the
    /// XAML is in device-independent ones. On a 150% display the difference is
    /// a third of the window, and the controls come out cropped.
    /// </remarks>
    private void ResizeToDips(int width, int height)
    {
        var handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        var scale = GetDpiForWindow(handle) / 96.0;
        if (scale <= 0)
        {
            scale = 1.0;
        }
        var area = Microsoft.UI.Windowing.DisplayArea.GetFromWindowId(
            AppWindow.Id, Microsoft.UI.Windowing.DisplayAreaFallback.Primary).WorkArea;
        AppWindow.Resize(new Windows.Graphics.SizeInt32(
            Math.Min((int)Math.Round(width * scale), area.Width),
            Math.Min((int)Math.Round(height * scale), area.Height)));
    }

    private void Dispatch(Action action) => DispatcherQueue.TryEnqueue(() => action());

    private string Tracer =>
        (TracerBox.SelectedItem as ComboBoxItem)?.Tag as string ?? "canny";

    // One slider, two numbers. Nobody wants a hand that draws instantly or a
    // machine that trembles, so the two only ever moved together anyway.
    private double Speed => 8.0 * Math.Pow(0.075, FeelSlider.Value / 10.0);

    private double Human => Math.Max(0.0, (FeelSlider.Value - 4.0) / 3.0);

    // ------------------------------------------------------------------ devices

    private async void OnRefreshDevices(object sender, RoutedEventArgs args) =>
        await RefreshDevicesAsync();

    private async Task RefreshDevicesAsync()
    {
        if (_engine is null)
        {
            return;
        }

        try
        {
            var result = await _engine.CallAsync("devices");
            var devices = result["devices"]?.AsArray() ?? new JsonArray();

            DeviceBox.Items.Clear();
            foreach (var device in devices)
            {
                var serial = device?["serial"]?.GetValue<string>() ?? "?";
                var description = device?["description"]?.GetValue<string>() ?? "";
                DeviceBox.Items.Add(new ComboBoxItem { Content = $"{serial} — {description}", Tag = serial });
            }

            if (DeviceBox.Items.Count > 0)
            {
                // By item, not by index. Setting SelectedIndex on a ComboBox
                // whose items were added moments earlier does not always take,
                // and the box then shows "Looking for a device…" over a device
                // that is connected and mirroring - which reads as a failure.
                DeviceBox.SelectedItem = DeviceBox.Items[0];
                StatusText.Text = $"{DeviceBox.Items.Count} device(s) found.";

                // With one device there is nothing to choose, and the live view
                // is the reason the window is worth looking at. Making people
                // press Connect first only delays the useful part.
                if (DeviceBox.Items.Count == 1 && !_connected
                    && devices[0]?["state"]?.GetValue<string>() == "device")
                {
                    OnConnect(this, new RoutedEventArgs());
                }
            }
            else
            {
                // The engine restarts the adb daemon before reporting nothing,
                // so by this point "none" means none rather than "the daemon
                // has been sulking since before the cable went in".
                StatusText.Text = "No device, and restarting adb did not find one. " +
                                  "Check the cable, turn on USB debugging, and accept the prompt on the phone.";
            }
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
    }

    private async void OnConnect(object sender, RoutedEventArgs args)
    {
        if (_engine is null)
        {
            return;
        }

        var serial = (DeviceBox.SelectedItem as ComboBoxItem)?.Tag as string;
        Busy.IsActive = true;
        try
        {
            var result = await _engine.CallAsync("connect", serial is null ? null : new { serial });
            var width = result["width"]!.GetValue<int>();
            var height = result["height"]!.GetValue<int>();
            var raw = result["raw_touch"]!.GetValue<bool>();

            _connected = true;
            ShapeToDevice(width, height);
            DeviceText.Text = $"{result["serial"]!.GetValue<string>()} · {width}×{height}";
            StatusText.Text = raw
                ? "Connected. This device allows raw touch events, which is the fast path."
                : "Connected. This device refuses raw touch events, so drawing goes through the injector.";
            UpdateButtons();

            PreviewHint.Text = "Starting the live view…";
            await _engine.CallAsync("mirror", new { on = true });
            PreviewHint.Visibility = Visibility.Collapsed;

            await RefreshPreviewAsync();
            await RefreshEstimateAsync();
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
            PreviewHint.Text = "Connect a device to see its screen here.";
        }
        finally
        {
            Busy.IsActive = false;
        }
    }

    /// <summary>Give the on-screen phone the proportions of the real one.</summary>
    /// <remarks>
    /// Called again for every frame whose shape differs from the last, because
    /// a phone that is turned reports the same `wm size` as before. Without it
    /// a landscape screen is squeezed into the portrait frame it was given at
    /// connect, and everything on it is drawn narrow.
    /// </remarks>
    private void ShapeToDevice(int width, int height)
    {
        if (width <= 0 || height <= 0)
        {
            return;
        }
        var scale = 780.0 / Math.Max(width, height);
        // The frame's padding is its bezel, and it is outside the screen area.
        var frameWidth = Math.Round(width * scale) + 18;
        var frameHeight = Math.Round(height * scale) + 18;
        if (Math.Abs(PhoneFrame.Width - frameWidth) < 0.5
            && Math.Abs(PhoneFrame.Height - frameHeight) < 0.5)
        {
            return;
        }
        PhoneFrame.Width = frameWidth;
        PhoneFrame.Height = frameHeight;
    }

    private void ShowFrame(string path, int width, int height)
    {
        ShapeToDevice(width, height);
        try
        {
            // Read the bytes rather than pointing a BitmapImage at the file: the
            // engine is writing the next frame while this one is being shown,
            // and a BitmapImage holds its file open.
            var bytes = File.ReadAllBytes(path);
            var bitmap = new BitmapImage();
            using var stream = new MemoryStream(bytes).AsRandomAccessStream();
            bitmap.SetSource(stream);
            MirrorImage.Source = bitmap;
        }
        catch (IOException)
        {
            // Caught the file mid-write; the next frame is 300 ms away.
        }
    }

    // -------------------------------------------------------------------- image

    private async void OnLoadImage(object sender, RoutedEventArgs args)
    {
        if (_engine is null)
        {
            return;
        }

        var picker = new FileOpenPicker();
        // An unpackaged app has no implicit window to hang a picker on.
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeFilter.Add(".png");
        picker.FileTypeFilter.Add(".jpg");
        picker.FileTypeFilter.Add(".jpeg");
        picker.FileTypeFilter.Add(".bmp");
        picker.FileTypeFilter.Add(".webp");

        var file = await picker.PickSingleFileAsync();
        if (file is null)
        {
            return;
        }

        try
        {
            var result = await _engine.CallAsync("load_image", new { path = file.Path });
            _imageLoaded = true;
            ImageText.Text = $"{Path.GetFileName(file.Path)} · " +
                             $"{result["width"]!.GetValue<int>()}×{result["height"]!.GetValue<int>()}";
            await RefreshPreviewAsync();
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
    }

    /// <summary>Open an image named on the command line, so the app can be the
    /// thing you send a picture to rather than a place you go and fetch one.</summary>
    private async Task OpenFromCommandLineAsync()
    {
        var named = Environment.GetCommandLineArgs().Skip(1)
            .FirstOrDefault(argument => File.Exists(argument));
        if (named is null || _engine is null)
        {
            return;
        }

        try
        {
            var result = await _engine.CallAsync("load_image", new { path = named });
            _imageLoaded = true;
            ImageText.Text = $"{Path.GetFileName(named)} · " +
                             $"{result["width"]!.GetValue<int>()}×{result["height"]!.GetValue<int>()}";
            await RefreshPreviewAsync();
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
    }

    private void OnSettingChanged(object sender, RoutedEventArgs args) => SchedulePreview();

    private void OnSliderChanged(object sender, RangeBaseValueChangedEventArgs args)
    {
        if (DetailText is not null)
        {
            DetailText.Text = $"{DetailSlider.Value:0} — {DetailWord(DetailSlider.Value)}";
        }
        SchedulePreview();
    }

    private static string DetailWord(double value) => value switch
    {
        <= 2 => "the shape and little else",
        <= 4 => "the main lines",
        <= 6 => "a moderate amount",
        <= 8 => "a fair amount",
        _ => "everything it can find",
    };

    private void SchedulePreview()
    {
        if (!_imageLoaded || _drawing)
        {
            return;
        }
        _previewDelay.Stop();
        _previewDelay.Start();
    }

    private async Task RefreshPreviewAsync()
    {
        if (_engine is null || !_imageLoaded)
        {
            return;
        }

        Busy.IsActive = true;
        try
        {
            var result = await _engine.CallAsync("preview", new
            {
                sensitivity = DetailSlider.Value,
                detail = DetailSlider.Value,
                method = Tracer,
                margin = Margin,
            });

            var overlay = result["overlay"]?.GetValue<string>();
            if (overlay is not null)
            {
                ShowOverlay(overlay);
            }

            StatusText.Text = $"{result["strokes"]!.GetValue<int>()} strokes, " +
                              $"{result["points"]!.GetValue<int>()} points, traced in " +
                              $"{result["seconds"]!.GetValue<double>():0.0}s";
            UpdateButtons();
            await RefreshEstimateAsync();
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
        finally
        {
            Busy.IsActive = false;
        }
    }

    private void ShowOverlay(string path)
    {
        // Copied first: the engine overwrites this file on every preview, and a
        // BitmapImage bound straight to it would hold the file open.
        var copy = Path.Combine(Path.GetTempPath(), $"mthread_draw_overlay_{Guid.NewGuid():N}.png");
        File.Copy(path, copy, overwrite: true);
        OverlayImage.Source = new BitmapImage(new Uri(copy));
    }

    // ------------------------------------------------------------------ pacing

    private async void OnPacingChanged(object sender, RangeBaseValueChangedEventArgs args)
    {
        if (FeelText is null)
        {
            return;  // fired while the XAML is still being built
        }

        FeelText.Text = FeelSlider.Value switch
        {
            0 => "instantly",
            <= 2 => $"very fast — {Speed:0.0}x",
            <= 4 => $"fast — {Speed:0.0}x",
            <= 6 => $"like a quick hand — {Speed:0.0}x",
            <= 8 => $"like a hand — {Speed:0.0}x",
            _ => $"like a careful hand — {Speed:0.0}x",
        };
        await RefreshEstimateAsync();
    }

    private async Task RefreshEstimateAsync()
    {
        if (_engine is null || !_connected || !_imageLoaded)
        {
            return;
        }

        try
        {
            var result = await _engine.CallAsync("estimate", new { speed = Speed, human = Human });
            var seconds = result["seconds"]!.GetValue<double>();
            EstimateText.Text = seconds >= 60
                ? $"About {(int)seconds / 60} min {(int)seconds % 60} s to draw."
                : $"About {seconds:0} s to draw.";
        }
        catch (EngineException)
        {
            EstimateText.Text = string.Empty;
        }
    }

    // ----------------------------------------------------------------- drawing

    private async void OnDraw(object sender, RoutedEventArgs args)
    {
        if (_engine is null)
        {
            return;
        }

        _drawing = true;
        UpdateButtons();
        Progress.Value = 0;

        try
        {
            var result = await _engine.CallAsync("draw", new
            {
                margin = Margin,
                speed = Speed,
                human = Human,
            });
            StatusText.Text = result["stopped"]!.GetValue<bool>()
                ? "Stopped."
                : $"Finished. {result["strokes"]!.GetValue<int>()} strokes drawn.";
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
        finally
        {
            _drawing = false;
            Progress.Value = 0;
            UpdateButtons();
        }
    }

    private async void OnStop(object sender, RoutedEventArgs args)
    {
        if (_engine is not null)
        {
            await _engine.PostAsync("stop");
            StatusText.Text = "Stopping…";
        }
    }

    private void UpdateButtons()
    {
        DrawButton.IsEnabled = _connected && _imageLoaded && !_drawing;
        StopButton.IsEnabled = _drawing;
        LoadButton.IsEnabled = !_drawing;
        ConnectButton.IsEnabled = !_drawing;
    }
}
