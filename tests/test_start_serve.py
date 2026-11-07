"""مُطلق ميزان عند الدخول: لا نسخة ثانية إن كان المنفذ مشغولًا."""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import start_serve  # noqa: E402


def test_listening_detects_an_occupied_port_and_a_free_one():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    assert start_serve.listening(port) is True
    s.close()
    assert start_serve.listening(port) is False


def test_main_does_not_spawn_when_port_is_busy(monkeypatch, tmp_path):
    monkeypatch.setattr(start_serve, "LOG", str(tmp_path / "l.log"))
    monkeypatch.setattr(start_serve, "listening", lambda port=0: True)
    spawned = []
    monkeypatch.setattr(start_serve.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    assert start_serve.main() == 0 and spawned == []
