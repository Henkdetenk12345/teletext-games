import time
import uuid
import threading

from minesweeper import Board


class PagePool:
    def __init__(self, magazine, subpage_start, subpage_end):
        self.magazine = magazine
        self._free = list(range(subpage_start, subpage_end + 1))
        self._lock = threading.Lock()

    def allocate(self):
        with self._lock:
            if not self._free:
                return None
            sub = self._free.pop(0)
            return int(f"{self.magazine}{sub:02d}", 16)

    def release(self, page_hex):
        with self._lock:
            page_str = f"{page_hex:x}"
            sub = int(page_str[1:])
            if sub not in self._free:
                self._free.append(sub)
                self._free.sort()


class Session:
    def __init__(self, session_id, page, board):
        self.session_id = session_id
        self.page = page
        self.board = board
        self.last_active = time.time()

    def touch(self):
        self.last_active = time.time()


class SessionManager:
    def __init__(self, page_pool, board_config, timeout_seconds):
        self.pool = page_pool
        self.board_config = board_config
        self.timeout_seconds = timeout_seconds
        self.sessions = {}
        self._lock = threading.Lock()

    def create_session(self):
        page = self.pool.allocate()
        if page is None:
            return None
        session_id = uuid.uuid4().hex
        board = Board(
            self.board_config["width"],
            self.board_config["height"],
            self.board_config["mines"],
        )
        session = Session(session_id, page, board)
        with self._lock:
            self.sessions[session_id] = session
        return session

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def end_session(self, session_id):
        with self._lock:
            session = self.sessions.pop(session_id, None)
        if session is not None:
            self.pool.release(session.page)
        return session

    def sweep_expired(self):
        now = time.time()
        expired_ids = [
            sid
            for sid, s in self.sessions.items()
            if now - s.last_active > self.timeout_seconds
        ]
        return [self.end_session(sid) for sid in expired_ids]
