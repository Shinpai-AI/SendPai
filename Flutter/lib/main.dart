import 'package:flutter/material.dart';
import 'dart:io';
import 'dart:convert';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:archive/archive.dart';
import 'package:desktop_drop/desktop_drop.dart';
import 'package:window_manager/window_manager.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  if (Platform.isLinux || Platform.isWindows || Platform.isMacOS) {
    await windowManager.ensureInitialized();

    // Icon Pfad relativ zum Executable
    final exeDir = p.dirname(Platform.resolvedExecutable);
    String iconPath = p.join(exeDir, 'sendpai-icon.png');
    if (!File(iconPath).existsSync()) {
      iconPath = p.join(exeDir, 'data', 'flutter_assets', 'assets', 'icon.png');
    }

    WindowOptions windowOptions = const WindowOptions(
      size: Size(520, 750),
      minimumSize: Size(400, 600),
      title: 'SendPai',
      center: true,
    );

    await windowManager.waitUntilReadyToShow(windowOptions, () async {
      await windowManager.show();
      await windowManager.focus();

      // Icon NACH show setzen — Window muss existieren!
      await Future.delayed(const Duration(milliseconds: 500));
      final absIconPath = File(iconPath).existsSync() ? File(iconPath).absolute.path : '';
      if (absIconPath.isNotEmpty) {
        await windowManager.setIcon(absIconPath);
      }
    });
  }

  runApp(const SendPaiApp());
}

class SendPaiApp extends StatelessWidget {
  const SendPaiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SendPai',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF1a1720),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFa832b8),
          secondary: Color(0xFFe8724a),
          surface: Color(0xFF2a2632),
        ),
        useMaterial3: true,
      ),
      home: const SendPaiHome(),
    );
  }
}

class SendPaiHome extends StatefulWidget {
  const SendPaiHome({super.key});

  @override
  State<SendPaiHome> createState() => _SendPaiHomeState();
}

class _SendPaiHomeState extends State<SendPaiHome> {
  List<String> sharedFiles = [];
  HttpServer? _server;
  bool isSharing = false;
  String localIP = '';
  String? publicIP;
  String packageName = 'SendPai-Dateien';
  int downloadCount = 0;
  List<String> activityLog = [];
  final int port = 7777;
  bool showPublicLink = false;

  @override
  void dispose() {
    _stopSharing();
    super.dispose();
  }

  Future<String> _getLocalIP() async {
    try {
      final interfaces = await NetworkInterface.list(
        type: InternetAddressType.IPv4,
        includeLinkLocal: false,
      );
      for (var iface in interfaces) {
        for (var addr in iface.addresses) {
          if (!addr.isLoopback) return addr.address;
        }
      }
    } catch (_) {}
    return '127.0.0.1';
  }

  Future<String?> _getPublicIP() async {
    for (var url in ['https://api.ipify.org', 'http://ifconfig.me/ip']) {
      try {
        final client = HttpClient();
        client.badCertificateCallback = (_, __, ___) => true;
        final request = await client.getUrl(Uri.parse(url)).timeout(const Duration(seconds: 5));
        final response = await request.close();
        final body = await response.transform(utf8.decoder).join();
        client.close();
        if (body.trim().isNotEmpty) return body.trim();
      } catch (_) {}
    }
    return null;
  }

  Future<void> _startSharing() async {
    if (sharedFiles.isEmpty) {
      _showSnackbar('Keine Dateien ausgewählt!');
      return;
    }
    try {
      localIP = await _getLocalIP();
      _server = await HttpServer.bind(InternetAddress.anyIPv4, port);
      setState(() => isSharing = true);
      _addLog('🚀 Server gestartet!');
      _addLog('🏠 Lokal: http://$localIP:$port');

      _getPublicIP().then((ip) {
        if (ip != null && mounted) {
          setState(() => publicIP = ip);
          _addLog('🌐 Internet: http://$ip:$port');
        } else if (mounted) {
          _addLog('🌐 Öffentliche IP nicht ermittelt');
        }
      });

      _server!.listen(_handleRequest, onError: (e) => _addLog('❌ Server Error: $e'));
    } catch (e) {
      _showSnackbar('Fehler: $e');
      _addLog('❌ $e');
    }
  }

  void _stopSharing() {
    _server?.close(force: true);
    _server = null;
    if (mounted) {
      setState(() {
        isSharing = false;
        publicIP = null;
        showPublicLink = false;
      });
      _addLog('⏹ Gestoppt');
    }
  }

  Future<void> _handleRequest(HttpRequest request) async {
    try {
      final path = request.uri.path;
      if (path == '/' || path == '/download') {
        await _serveDownloadPage(request);
        _addLog('👀 Besucher: ${request.connectionInfo?.remoteAddress.address}');
      } else if (path == '/download/all') {
        await _serveZip(request);
      } else if (path.startsWith('/download/file/')) {
        await _serveSingleFile(request);
      } else if (path == '/api/info') {
        request.response
          ..headers.contentType = ContentType.json
          ..headers.set('Access-Control-Allow-Origin', '*')
          ..write(jsonEncode({'app': 'SendPai', 'files': sharedFiles.length}));
        await request.response.close();
      } else {
        request.response.statusCode = 404;
        await request.response.close();
      }
    } catch (_) {}
  }

  Future<void> _serveDownloadPage(HttpRequest request) async {
    var fileListHtml = '';
    int totalSize = 0;
    for (int i = 0; i < sharedFiles.length; i++) {
      final isDir = FileSystemEntity.isDirectorySync(sharedFiles[i]);
      int size = 0;
      if (!isDir) {
        try { size = await File(sharedFiles[i]).length(); } catch (_) {}
      }
      totalSize += size;
      final name = p.basename(sharedFiles[i]);
      final sizeStr = isDir ? 'Ordner' : (size > 1048576 ? '${(size / 1048576).toStringAsFixed(1)} MB' : '${(size / 1024).toStringAsFixed(0)} KB');
      fileListHtml += '<a href="/download/file/$i" download style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:#2a2632;border-radius:12px;margin:8px 0;text-decoration:none;border:1px solid #33303c;"><span style="color:#f0ece4;">📄 $name</span><div style="display:flex;align-items:center;gap:12px;"><span style="color:#8a8a9a;">$sizeStr</span><span style="background:linear-gradient(135deg,#a832b8,#e8724a);color:white;padding:10px 24px;border-radius:8px;font-weight:bold;">⬇️ Download</span></div></a>';
    }
    final totalStr = totalSize > 1048576 ? '${(totalSize / 1048576).toStringAsFixed(1)} MB' : '${(totalSize / 1024).toStringAsFixed(0)} KB';
    final allBtn = sharedFiles.length > 1
        ? "<a href='/download/all' download style='display:block;text-align:center;background:linear-gradient(135deg,#a832b8,#e8724a);color:white;padding:18px;border-radius:12px;text-decoration:none;font-weight:bold;font-size:1.2em;margin:20px 0;'>📦 Alles als ZIP</a>"
        : "<a href='/download/file/0' download style='display:block;text-align:center;background:linear-gradient(135deg,#a832b8,#e8724a);color:white;padding:18px;border-radius:12px;text-decoration:none;font-weight:bold;font-size:1.2em;margin:20px 0;'>⬇️ Herunterladen</a>";
    final html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SendPai</title><style>body{background:#1a1720;color:#f0ece4;font-family:-apple-system,sans-serif;margin:0;padding:20px;}.c{max-width:600px;margin:0 auto;}h1{text-align:center;font-size:2em;}.s{text-align:center;color:#8a8a9a;}.f{text-align:center;color:#8a8a9a;font-size:0.8em;margin-top:40px;}</style></head><body><div class="c"><h1>📤 SendPai</h1><p class="s">${sharedFiles.length} Datei${sharedFiles.length != 1 ? 'en' : ''} • $totalStr</p>$allBtn$fileListHtml<p class="f">⚠️ Nur für den vorgesehenen Empfänger.<br>SendPai by Shinpai-AI • shinpai.de</p></div></body></html>';
    request.response
      ..headers.contentType = ContentType.html
      ..write(html);
    await request.response.close();
  }

  Future<void> _serveSingleFile(HttpRequest request) async {
    try {
      final idx = int.parse(request.uri.pathSegments.last);
      final filePath = sharedFiles[idx];
      final name = p.basename(filePath);

      if (FileSystemEntity.isDirectorySync(filePath)) {
        // Ordner als ZIP senden
        final archive = Archive();
        final dir = Directory(filePath);
        for (var f in dir.listSync(recursive: true).whereType<File>()) {
          final relativePath = p.relative(f.path, from: filePath);
          final bytes = await f.readAsBytes();
          archive.addFile(ArchiveFile(relativePath, bytes.length, bytes));
        }
        final zipData = ZipEncoder().encode(archive);
        if (zipData == null) return;
        request.response
          ..headers.set('Content-Type', 'application/zip')
          ..headers.set('Content-Disposition', 'attachment; filename="$name.zip"')
          ..headers.set('Content-Length', '${zipData.length}')
          ..add(zipData);
        await request.response.close();
      } else {
        final file = File(filePath);
        final size = await file.length();
        request.response
          ..headers.set('Content-Type', 'application/octet-stream')
          ..headers.set('Content-Disposition', 'attachment; filename="$name"')
          ..headers.set('Content-Length', '$size');
        await file.openRead().pipe(request.response);
      }
      _addLog('⬇️ $name → ${request.connectionInfo?.remoteAddress.address}');
      if (mounted) setState(() => downloadCount++);
    } catch (_) {
      request.response.statusCode = 404;
      await request.response.close();
    }
  }

  Future<void> _serveZip(HttpRequest request) async {
    try {
      final archive = Archive();
      for (var filePath in sharedFiles) {
        if (FileSystemEntity.isDirectorySync(filePath)) {
          final dir = Directory(filePath);
          final dirName = p.basename(filePath);
          for (var f in dir.listSync(recursive: true).whereType<File>()) {
            final relativePath = '$dirName/${p.relative(f.path, from: filePath)}';
            final bytes = await f.readAsBytes();
            archive.addFile(ArchiveFile(relativePath, bytes.length, bytes));
          }
        } else {
          final file = File(filePath);
          final bytes = await file.readAsBytes();
          archive.addFile(ArchiveFile(p.basename(filePath), bytes.length, bytes));
        }
      }
      final zipData = ZipEncoder().encode(archive);
      if (zipData == null) return;
      final zipName = '$packageName.zip';
      request.response
        ..headers.set('Content-Type', 'application/zip')
        ..headers.set('Content-Disposition', 'attachment; filename="$zipName"')
        ..headers.set('Content-Length', '${zipData.length}')
        ..add(zipData);
      await request.response.close();
      _addLog('⬇️ $zipName → ${request.connectionInfo?.remoteAddress.address}');
      if (mounted) setState(() => downloadCount++);
    } catch (_) {
      request.response.statusCode = 500;
      await request.response.close();
    }
  }

  void _addLog(String msg) {
    if (!mounted) return;
    final t = DateTime.now();
    setState(() {
      activityLog.insert(0, '[${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}:${t.second.toString().padLeft(2, '0')}] $msg');
      if (activityLog.length > 50) activityLog.removeLast();
    });
  }

  void _showSnackbar(String msg) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  Future<void> _pickFiles() async {
    final result = await FilePicker.platform.pickFiles(allowMultiple: true);
    if (result != null) {
      setState(() {
        for (var file in result.files) {
          if (file.path != null && !sharedFiles.contains(file.path!)) {
            sharedFiles.add(file.path!);
          }
        }
      });
    }
  }

  Future<void> _pickFolder() async {
    final result = await FilePicker.platform.getDirectoryPath();
    if (result != null && !sharedFiles.contains(result)) {
      setState(() => sharedFiles.add(result));
    }
  }

  void _onDrop(DropDoneDetails details) {
    setState(() {
      for (var file in details.files) {
        final path = file.path;
        if (!sharedFiles.contains(path)) sharedFiles.add(path);
      }
    });
  }

  bool _isDragging = false;

  String _formatSize(int bytes) {
    if (bytes > 1048576) return '${(bytes / 1048576).toStringAsFixed(1)} MB';
    return '${(bytes / 1024).toStringAsFixed(0)} KB';
  }

  int _totalSize() {
    int total = 0;
    for (var f in sharedFiles) {
      try { total += File(f).lengthSync(); } catch (_) {}
    }
    return total;
  }

  String get _currentLink => showPublicLink && publicIP != null ? 'http://$publicIP:$port' : 'http://$localIP:$port';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 10),
              Center(child: ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Image.asset('assets/icon.png', width: 64, height: 64))),
              const SizedBox(height: 8),
              const Text('SendPai', textAlign: TextAlign.center, style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold)),
              const Text('Dateien senden wie ein Senpai!', textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF8a8a9a), fontSize: 13)),
              const SizedBox(height: 20),
              _label('📁 DATEIEN'),
              const SizedBox(height: 8),
              Row(children: [
                _btn('📄 Dateien', _pickFiles),
                const SizedBox(width: 8),
                _btn('📂 Ordner', _pickFolder),
                const Spacer(),
                if (sharedFiles.isNotEmpty) _btn('🗑️', () => setState(() => sharedFiles.clear()), color: const Color(0xFF8a8a9a)),
              ]),
              const SizedBox(height: 8),
              DropTarget(
                onDragDone: _onDrop,
                onDragEntered: (_) => setState(() => _isDragging = true),
                onDragExited: (_) => setState(() => _isDragging = false),
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF33303c),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: _isDragging ? const Color(0xFFa832b8) : Colors.transparent,
                      width: 2,
                    ),
                  ),
                  constraints: const BoxConstraints(minHeight: 80, maxHeight: 150),
                  child: sharedFiles.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(_isDragging ? Icons.file_download : Icons.cloud_upload_outlined,
                                  color: _isDragging ? const Color(0xFFa832b8) : const Color(0xFF8a8a9a), size: 32),
                              const SizedBox(height: 8),
                              Text(_isDragging ? 'Loslassen!' : 'Dateien hierher ziehen',
                                  style: TextStyle(color: _isDragging ? const Color(0xFFa832b8) : const Color(0xFF8a8a9a))),
                            ],
                          ),
                        )
                      : ListView.builder(
                          shrinkWrap: true, itemCount: sharedFiles.length,
                          itemBuilder: (_, i) {
                            final isDir = FileSystemEntity.isDirectorySync(sharedFiles[i]);
                            final icon = isDir ? '📂' : '📄';
                            int size = 0;
                            if (!isDir) { try { size = File(sharedFiles[i]).lengthSync(); } catch (_) {} }
                            return ListTile(dense: true,
                              title: Text('$icon ${p.basename(sharedFiles[i])}', style: const TextStyle(fontSize: 13)),
                              trailing: Text(isDir ? 'Ordner' : _formatSize(size),
                                style: const TextStyle(color: Color(0xFF8a8a9a), fontSize: 12)));
                          }),
                ),
              ),
              if (sharedFiles.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4),
                child: Text('${sharedFiles.length} Dateien • ${_formatSize(_totalSize())}', style: const TextStyle(color: Color(0xFF8a8a9a), fontSize: 12))),
              const SizedBox(height: 12),
              _label('📦 PAKETNAME (für ZIP)'),
              const SizedBox(height: 6),
              TextField(
                decoration: InputDecoration(filled: true, fillColor: const Color(0xFF33303c),
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                  hintText: 'SendPai-Dateien', hintStyle: const TextStyle(color: Color(0xFF8a8a9a))),
                style: const TextStyle(color: Color(0xFFf0ece4)),
                onChanged: (v) => packageName = v.isEmpty ? 'SendPai-Dateien' : v),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: isSharing ? _stopSharing : _startSharing,
                style: ElevatedButton.styleFrom(
                  backgroundColor: isSharing ? const Color(0xFFc0392b) : const Color(0xFF00b464),
                  foregroundColor: isSharing ? Colors.white : const Color(0xFF1a1720),
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                child: Text(isSharing ? '⏹  STOPPEN' : '🚀  BEREITSTELLEN')),
              const SizedBox(height: 12),
              if (isSharing) Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(color: const Color(0xFF2a2632), borderRadius: BorderRadius.circular(12)),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  const Text('🟢 Bereit! Link kopieren und teilen:', style: TextStyle(color: Color(0xFF00b464), fontSize: 13)),
                  const SizedBox(height: 12),
                  Row(children: [
                    Expanded(child: Container(padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      decoration: BoxDecoration(color: const Color(0xFF33303c), borderRadius: BorderRadius.circular(8)),
                      child: Text(_currentLink, style: const TextStyle(color: Color(0xFF3498db), fontSize: 13, fontFamily: 'monospace')))),
                    const SizedBox(width: 8),
                  ]),
                  const SizedBox(height: 10),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: () { Clipboard.setData(ClipboardData(text: _currentLink)); _showSnackbar('📋 Link kopiert!'); _addLog('📋 Link kopiert!'); },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFFa832b8),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))),
                      child: const Text('📋  Kopieren', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Colors.white)))),
                  const SizedBox(height: 10),
                  if (publicIP != null) TextButton(
                    onPressed: () => setState(() => showPublicLink = !showPublicLink),
                    child: Text(showPublicLink ? '🏠 Lokal-Link' : '🌐 Internet-Link', style: const TextStyle(color: Color(0xFFe8724a)))),
                  const SizedBox(height: 6),
                  Text(publicIP != null
                    ? '🏠 Gleiches WLAN: Sofort nutzbar!\n🌐 Internet: Port $port im Router freigeben!'
                    : '🏠 Gleiches WLAN: Sofort nutzbar!\n🌐 Öffentliche IP nicht ermittelt.\n    Browser: https://api.ipify.org',
                    style: const TextStyle(color: Color(0xFF8a8a9a), fontSize: 11)),
                  const SizedBox(height: 6),
                  const Text('⚠️ Link nur an den gewünschten Empfänger teilen!', style: TextStyle(color: Color(0xFF8a8a9a), fontSize: 11)),
                ])),
              const SizedBox(height: 12),
              if (downloadCount > 0) Center(child: Column(children: [
                Text('$downloadCount', style: const TextStyle(fontSize: 36, fontWeight: FontWeight.bold, color: Color(0xFFa832b8))),
                const Text('DOWNLOADS', style: TextStyle(color: Color(0xFF8a8a9a), fontSize: 10, letterSpacing: 2))])),
              const SizedBox(height: 12),
              _label('📋 AKTIVITÄT'),
              const SizedBox(height: 6),
              Container(height: 120, decoration: BoxDecoration(color: const Color(0xFF33303c), borderRadius: BorderRadius.circular(12)),
                child: activityLog.isEmpty
                  ? const Center(child: Text('Keine Aktivität', style: TextStyle(color: Color(0xFF8a8a9a), fontSize: 12)))
                  : ListView.builder(padding: const EdgeInsets.all(10), itemCount: activityLog.length,
                      itemBuilder: (_, i) => Text(activityLog[i], style: TextStyle(fontSize: 11, fontFamily: 'monospace',
                        color: activityLog[i].contains('⬇️') ? const Color(0xFF00b464)
                          : activityLog[i].contains('🌐') ? const Color(0xFFe8724a) : const Color(0xFF8a8a9a))))),
              const SizedBox(height: 12),
              const Text('shinpai.de | AGPL-3.0', textAlign: TextAlign.center, style: TextStyle(color: Color(0xFF8a8a9a), fontSize: 10)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _label(String text) => Text(text, style: const TextStyle(color: Color(0xFFe8724a), fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1));
  Widget _btn(String text, VoidCallback onPressed, {Color? color}) => ElevatedButton(
    onPressed: onPressed,
    style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF2a2632), foregroundColor: color ?? const Color(0xFFf0ece4),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
    child: Text(text, style: const TextStyle(fontSize: 13)));
}
