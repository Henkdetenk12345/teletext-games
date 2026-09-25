import json
import threading
import time
import traceback

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from vbit2interface import interface

from session_manager import PagePool, SessionManager
import teletext_render

with open("config.json") as f:
    CONFIG = json.load(f)

pool = PagePool(
    CONFIG["page_pool"]["magazine"],
    CONFIG["page_pool"]["subpage_start"],
    CONFIG["page_pool"]["subpage_end"],
)
manager = SessionManager(pool, CONFIG["minesweeper"], CONFIG["session_timeout_seconds"])

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=CONFIG["api"]["cors_origins"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def push_full_page(page):
    c = interface.Client(CONFIG["vbit2"]["host"], CONFIG["vbit2"]["port"])
    c.setChannel(0)
    c.deletePage(page)
    c.openPage(page)
    c.setSubPage(0x0000)
    c.setSubPageOptions(erase=True)
    for row_number, data in teletext_render.STATIC_ROWS.items():
        if row_number == 0:
            continue
        c.setRow(row_number, data)
    c.close()


def push_dynamic_rows(page, session):
    rows = teletext_render.render_dynamic_rows(session.board)
    c = interface.Client(CONFIG["vbit2"]["host"], CONFIG["vbit2"]["port"])
    c.setChannel(0)
    c.openPage(page)
    c.setSubPage(0x0000)
    for row_number, data in rows.items():
        c.setRow(row_number, data)
    c.close()


def remove_page(page):
    c = interface.Client(CONFIG["vbit2"]["host"], CONFIG["vbit2"]["port"])
    c.setChannel(0)
    c.deletePage(page)
    c.close()


class MoveRequest(BaseModel):
    x: int
    y: int


@app.post("/call")
def call_in():
    session = manager.create_session()
    if session is None:
        return {"error": "geen pagina beschikbaar, probeer later opnieuw"}
    try:
        push_full_page(session.page)
        push_dynamic_rows(session.page, session)
    except Exception as e:
        manager.end_session(session.session_id)
        traceback.print_exc()
        return {"error": f"kon pagina niet naar VBIT2 sturen: {e}"}
    return {"session_id": session.session_id, "page": f"{session.page:x}"}


@app.get("/game/{session_id}")
def get_state(session_id: str):
    session = manager.get_session(session_id)
    if session is None:
        return {"error": "sessie niet gevonden of verlopen"}
    session.touch()
    state = session.board.to_dict()
    state["page"] = f"{session.page:x}"
    return state


@app.post("/game/{session_id}/reveal")
def reveal(session_id: str, move: MoveRequest):
    session = manager.get_session(session_id)
    if session is None:
        return {"error": "sessie niet gevonden of verlopen"}
    session.touch()
    session.board.reveal(move.x, move.y)
    try:
        push_dynamic_rows(session.page, session)
    except Exception as e:
        traceback.print_exc()
    return session.board.to_dict()


@app.post("/game/{session_id}/flag")
def flag(session_id: str, move: MoveRequest):
    session = manager.get_session(session_id)
    if session is None:
        return {"error": "sessie niet gevonden of verlopen"}
    session.touch()
    session.board.toggle_flag(move.x, move.y)
    try:
        push_dynamic_rows(session.page, session)
    except Exception as e:
        traceback.print_exc()
    return session.board.to_dict()


@app.post("/game/{session_id}/hangup")
def hangup(session_id: str):
    session = manager.end_session(session_id)
    if session is not None:
        remove_page(session.page)
    return {"ok": True}


def cleanup_loop():
    while True:
        time.sleep(30)
        for session in manager.sweep_expired():
            remove_page(session.page)


if __name__ == "__main__":
    threading.Thread(target=cleanup_loop, daemon=True).start()
    uvicorn.run(app, host=CONFIG["api"]["host"], port=CONFIG["api"]["port"])
