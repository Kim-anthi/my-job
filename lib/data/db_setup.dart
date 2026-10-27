/// Picks the SQLite backend at compile time.
///
/// Mobile uses the platform's own SQLite, desktop uses FFI, and the web uses a
/// WebAssembly build. The conditional export keeps web-only libraries out of
/// native builds (and `dart:io` out of web builds), which is what would
/// otherwise break compilation.
library;

export 'db_setup_io.dart'
    if (dart.library.js_interop) 'db_setup_web.dart';
