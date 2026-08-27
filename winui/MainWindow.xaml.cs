using System.Runtime.InteropServices.WindowsRuntime;
using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Pickers;

namespace MThreadDraw;

public sealed partial class MainWindow : Window
{
    private Engine? _engine;
    private bool _imageLoaded;
    private bool _connected;
    private bool _drawing;

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

        _placeDelay.Tick += async (_, _) =>
        {
            _placeDelay.Stop();
            await SendPlaceAsync();
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

    private void ShowFrameFile(string path) => ShowFrame(path, 0, 0);

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
            ShowLayers(await _engine.CallAsync("load_image", new { path = file.Path }));
            await RefreshEstimateAsync();
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
            ShowLayers(await _engine.CallAsync("load_image", new { path = named }));
            await RefreshEstimateAsync();
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
    }

    // ---------------------------------------------------------------- layers

    private bool _fillingLayerList;

    /// <summary>Redraw the layer list and the overlay from one engine reply.</summary>
    /// <remarks>
    /// Every layer operation answers with the whole state rather than a delta.
    /// It is a few hundred bytes and it removes an entire class of bug, the one
    /// where the list and the engine disagree about which layer is selected.
    /// </remarks>
    private void ShowLayers(JsonNode result)
    {
        var layers = result["layers"]?.AsArray();
        if (layers is null)
        {
            return;
        }

        _fillingLayerList = true;
        LayerList.Items.Clear();
        foreach (var layer in layers)
        {
            var name = layer?["name"]?.GetValue<string>() ?? "?";
            var strokes = layer?["strokes"]?.GetValue<int>() ?? 0;
            var erased = layer?["erased"]?.GetValue<int>() ?? 0;
            var visible = layer?["visible"]?.GetValue<bool>() ?? true;
            var label = $"{name} · {strokes} strokes";
            if (erased > 0)
            {
                label += $" · {erased} erased";
            }
            if (!visible)
            {
                label += " · hidden";
            }
            LayerList.Items.Add(new ListViewItem { Content = label, Opacity = visible ? 1.0 : 0.5 });
        }

        var current = result["current"]?.GetValue<int>() ?? 0;
        if (current >= 0 && current < LayerList.Items.Count)
        {
            LayerList.SelectedIndex = current;
        }
        _fillingLayerList = false;

        _imageLoaded = LayerList.Items.Count > 0;
        var overlay = result["overlay"]?.GetValue<string>();
        if (overlay is not null)
        {
            ShowOverlay(overlay);
        }
        else if (!_imageLoaded)
        {
            OverlayImage.Source = null;
        }

        ImageText.Text = _imageLoaded
            ? $"{LayerList.Items.Count} layer(s) · {result["strokes"]!.GetValue<int>()} strokes, " +
              $"{result["points"]!.GetValue<int>()} points"
            : "No image loaded";

        // The hint sits behind the overlay, so once there is a drawing to look
        // at it shows through it. The status bar says the same thing anyway.
        PreviewHint.Visibility = _imageLoaded || _connected
            ? Visibility.Collapsed
            : Visibility.Visible;
        UpdateButtons();
    }

    private async void OnLayerSelected(object sender, SelectionChangedEventArgs args)
    {
        if (_fillingLayerList || _engine is null || LayerList.SelectedIndex < 0)
        {
            return;
        }
        await Call("layer_select", new { index = LayerList.SelectedIndex });
    }

    private async void OnLayerRaise(object sender, RoutedEventArgs args) =>
        await Call("layer_raise", new { });

    private async void OnLayerRemove(object sender, RoutedEventArgs args) =>
        await Call("layer_remove", new { });

    private async void OnLayerHide(object sender, RoutedEventArgs args)
    {
        var hiding = (string)LayerHideButton.Content == "Hide";
        LayerHideButton.Content = hiding ? "Show" : "Hide";
        await Call("layer_visible", new { visible = !hiding });
    }

    /// <summary>Call an operation that answers with the whole layer state.</summary>
    private async Task Call(string operation, object arguments)
    {
        if (_engine is null)
        {
            return;
        }
        try
        {
            ShowLayers(await _engine.CallAsync(operation, arguments));
            await RefreshEstimateAsync();
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
    }

    // ----------------------------------------------------------------- tools

    private bool _erasing;

    private void OnToolChanged(object sender, RoutedEventArgs args)
    {
        _erasing = ReferenceEquals(sender, EraseToggle) && EraseToggle.IsChecked == true;
        MoveToggle.IsChecked = !_erasing;
        EraseToggle.IsChecked = _erasing;
        PlaceHint.Text = _erasing
            ? "Drag across strokes to take them out · Undo erase brings them back"
            : "Drag to move it · wheel to resize · Shift and wheel to turn · double-click to fit";
    }

    private async void OnUndoErase(object sender, RoutedEventArgs args) =>
        await Call("erase", new { undo = true });

    private async void OnFlipX(object sender, RoutedEventArgs args) =>
        await Call("place", new { flip_x = true });

    private async void OnFlipY(object sender, RoutedEventArgs args) =>
        await Call("place", new { flip_y = true });

    private async void OnFit(object sender, RoutedEventArgs args) =>
        await Call("place", new { reset = true });

    /// <summary>Take a screenshot copied off the phone by hand.</summary>
    /// <remarks>
    /// Capture fails on some devices and in some emulators, and when it does
    /// there is nothing to place a drawing against. A still picture of the same
    /// screen does not update, but it is enough to arrange a drawing on.
    /// </remarks>
    private async void OnUseStill(object sender, RoutedEventArgs args)
    {
        if (_engine is null)
        {
            return;
        }

        var picker = new FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeFilter.Add(".png");
        picker.FileTypeFilter.Add(".jpg");
        picker.FileTypeFilter.Add(".jpeg");

        var file = await picker.PickSingleFileAsync();
        if (file is null)
        {
            return;
        }

        try
        {
            var result = await _engine.CallAsync("still", new { path = file.Path });
            var width = result["width"]!.GetValue<int>();
            var height = result["height"]!.GetValue<int>();
            ShapeToDevice(width, height);
            ShowFrameFile(file.Path);
            PreviewHint.Visibility = Visibility.Collapsed;
            StatusText.Text = $"Using {Path.GetFileName(file.Path)} as the screen, {width}×{height}. " +
                              "It will not update; connect a device for the live view.";
            ShowLayers(result);
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
    }

    // ------------------------------------------------------------- placement

    private bool _draggingDrawing;
    private bool _erasingInFlight;
    private Windows.Foundation.Point _lastDrag;
    private double _pendingX, _pendingY, _pendingZoom = 1.0, _pendingTurn;

    /// <summary>Collects gestures and sends them at a rate the engine can meet.</summary>
    /// <remarks>
    /// A drag produces a pointer event per mouse report, and each one would
    /// otherwise be a round trip that re-renders the overlay. Coalescing keeps
    /// the drawing under the cursor without asking for sixty overlays a second.
    /// </remarks>
    private readonly DispatcherTimer _placeDelay = new() { Interval = TimeSpan.FromMilliseconds(70) };

    private async void OnStagePressed(object sender, PointerRoutedEventArgs args)
    {
        if (!_imageLoaded || _drawing)
        {
            return;
        }
        _draggingDrawing = true;
        _lastDrag = args.GetCurrentPoint(PhoneStage).Position;
        PhoneStage.CapturePointer(args.Pointer);
        if (_erasing)
        {
            await EraseAtAsync(args);
        }
    }

    private async void OnStageMoved(object sender, PointerRoutedEventArgs args)
    {
        if (!_draggingDrawing)
        {
            return;
        }
        if (_erasing)
        {
            await EraseAtAsync(args);
            return;
        }
        var here = args.GetCurrentPoint(PhoneStage).Position;
        // In fractions of the phone's own picture, so a drag of an inch moves
        // the drawing the same share of the screen whatever the window size.
        _pendingX += (here.X - _lastDrag.X) / Math.Max(1.0, PhoneScreen.ActualWidth);
        _pendingY += (here.Y - _lastDrag.Y) / Math.Max(1.0, PhoneScreen.ActualHeight);
        _lastDrag = here;
        SchedulePlace();
    }

    /// <summary>Erase where the pointer is, in fractions of the phone's screen.</summary>
    /// <remarks>
    /// Measured against the screen area rather than the window, so the same
    /// gesture erases the same strokes whatever size the window has been
    /// dragged to, and whichever way up the phone is being held.
    /// </remarks>
    private async Task EraseAtAsync(PointerRoutedEventArgs args)
    {
        if (_engine is null || _erasingInFlight)
        {
            return;
        }
        var point = args.GetCurrentPoint(PhoneScreen).Position;
        var x = point.X / Math.Max(1.0, PhoneScreen.ActualWidth);
        var y = point.Y / Math.Max(1.0, PhoneScreen.ActualHeight);
        if (x < 0 || x > 1 || y < 0 || y > 1)
        {
            return;
        }

        // One at a time: a drag reports faster than the engine can re-render an
        // overlay, and queueing every report would run behind the mouse.
        _erasingInFlight = true;
        try
        {
            ShowLayers(await _engine.CallAsync("erase", new { x, y, radius = 0.025 }));
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
        finally
        {
            _erasingInFlight = false;
        }
    }

    private void OnStageReleased(object sender, PointerRoutedEventArgs args)
    {
        _draggingDrawing = false;
        PhoneStage.ReleasePointerCapture(args.Pointer);
    }

    private void OnStageWheel(object sender, PointerRoutedEventArgs args)
    {
        if (!_connected || !_imageLoaded || _drawing)
        {
            return;
        }
        var point = args.GetCurrentPoint(PhoneStage);
        var notches = point.Properties.MouseWheelDelta / 120.0;
        if (point.Properties.IsHorizontalMouseWheel
            || args.KeyModifiers.HasFlag(Windows.System.VirtualKeyModifiers.Shift))
        {
            _pendingTurn += notches * 5.0;
        }
        else
        {
            _pendingZoom *= Math.Pow(1.1, notches);
        }
        args.Handled = true;
        SchedulePlace();
    }

    private async void OnStageDoubleTapped(object sender, DoubleTappedRoutedEventArgs args)
    {
        if (_engine is null || !_imageLoaded)
        {
            return;
        }
        await SendPlaceAsync(reset: true);
    }

    private void SchedulePlace()
    {
        _placeDelay.Stop();
        _placeDelay.Start();
    }

    private async Task SendPlaceAsync(bool reset = false)
    {
        if (_engine is null || !_imageLoaded)
        {
            return;
        }

        var dx = _pendingX;
        var dy = _pendingY;
        var zoom = _pendingZoom;
        var turn = _pendingTurn;
        _pendingX = _pendingY = _pendingTurn = 0;
        _pendingZoom = 1.0;

        try
        {
            var result = await _engine.CallAsync("place",
                reset ? new { reset = true } : (object)new { dx, dy, zoom, turn });
            ShowLayers(result);

            var layers = result["layers"]?.AsArray();
            var current = result["current"]?.GetValue<int>() ?? 0;
            if (layers is not null && current < layers.Count)
            {
                PlaceHint.Text = $"{layers[current]!["scale"]!.GetValue<double>():0.00}× · " +
                                 $"{layers[current]!["rotation"]!.GetValue<double>():0}° · " +
                                 "drag to move · wheel to resize · Shift and wheel to turn";
            }
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
            });

            ShowLayers(result);
            StatusText.Text = $"{result["strokes"]!.GetValue<int>()} strokes, " +
                              $"{result["points"]!.GetValue<int>()} points, traced in " +
                              $"{result["seconds"]!.GetValue<double>():0.0}s";
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
            var result = await _engine.CallAsync("draw", new { speed = Speed, human = Human });
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

    // ------------------------------------------------------ record and replay

    private bool _recording;
    private bool _haveSession;

    private async void OnRecord(object sender, RoutedEventArgs args)
    {
        if (_engine is null)
        {
            return;
        }

        try
        {
            if (!_recording)
            {
                await _engine.CallAsync("record_start");
                _recording = true;
                RecordButton.Content = "Stop recording";
                StatusText.Text = "Recording. Do something on the phone, then press stop.";
            }
            else
            {
                var result = await _engine.CallAsync("record_stop");
                _recording = false;
                RecordButton.Content = "Record";
                ShowSession(result);
            }
        }
        catch (EngineException error)
        {
            _recording = false;
            RecordButton.Content = "Record";
            StatusText.Text = error.Message;
        }
        UpdateButtons();
    }

    private void ShowSession(JsonNode result)
    {
        var strokes = result["strokes"]!.GetValue<int>();
        var points = result["points"]!.GetValue<int>();
        var seconds = result["seconds"]!.GetValue<double>();
        _haveSession = strokes > 0;

        var where = result["recorded_on"]?.GetValue<string>();
        var size = result["recorded_size"]?.AsArray();
        var origin = string.IsNullOrEmpty(where)
            ? string.Empty
            : $" · from {where}" + (size is null ? "" : $" at {size[0]}×{size[1]}");

        SessionText.Text = strokes == 0
            ? "Nothing was recorded — no touches were seen."
            : $"{strokes} strokes, {points} points, {seconds:0.0}s{origin}";
        StatusText.Text = _haveSession
            ? "Recording ready. It replays on any phone, scaled to that screen."
            : StatusText.Text;
    }

    private async void OnPlay(object sender, RoutedEventArgs args)
    {
        if (_engine is null)
        {
            return;
        }

        _drawing = true;
        UpdateButtons();
        try
        {
            var result = await _engine.CallAsync("play", new { speed = 1.0, repeat = 1 });
            StatusText.Text = result["stopped"]!.GetValue<bool>()
                ? "Stopped."
                : $"Replayed {result["strokes"]!.GetValue<int>()} strokes.";
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

    private async void OnOpenSession(object sender, RoutedEventArgs args)
    {
        if (_engine is null)
        {
            return;
        }

        var picker = new FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeFilter.Add(".json");

        var file = await picker.PickSingleFileAsync();
        if (file is null)
        {
            return;
        }

        try
        {
            ShowSession(await _engine.CallAsync("session_open", new { path = file.Path }));
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
        UpdateButtons();
    }

    private async void OnSaveSession(object sender, RoutedEventArgs args)
    {
        if (_engine is null)
        {
            return;
        }

        var picker = new FileSavePicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(this));
        picker.FileTypeChoices.Add("MThread recording", new List<string> { ".json" });
        picker.SuggestedFileName = "recording";

        var file = await picker.PickSaveFileAsync();
        if (file is null)
        {
            return;
        }

        try
        {
            await _engine.CallAsync("session_save", new { path = file.Path });
            StatusText.Text = $"Saved to {file.Path}";
        }
        catch (EngineException error)
        {
            StatusText.Text = error.Message;
        }
    }

    private void UpdateButtons()
    {
        DrawButton.IsEnabled = _connected && _imageLoaded && !_drawing;
        StopButton.IsEnabled = _drawing;
        LoadButton.IsEnabled = !_drawing;
        ConnectButton.IsEnabled = !_drawing;
        RecordButton.IsEnabled = _connected && !_drawing;
        LayerRaiseButton.IsEnabled = LayerList.Items.Count > 1 && !_drawing;
        LayerHideButton.IsEnabled = _imageLoaded && !_drawing;
        LayerRemoveButton.IsEnabled = _imageLoaded && !_drawing;
        UndoEraseButton.IsEnabled = _imageLoaded && !_drawing;
        FlipXButton.IsEnabled = _imageLoaded && !_drawing;
        FlipYButton.IsEnabled = _imageLoaded && !_drawing;
        FitButton.IsEnabled = _imageLoaded && !_drawing;
        PlayButton.IsEnabled = _connected && _haveSession && !_drawing && !_recording;
        OpenSessionButton.IsEnabled = !_drawing && !_recording;
        SaveSessionButton.IsEnabled = _haveSession && !_recording;
    }
}
