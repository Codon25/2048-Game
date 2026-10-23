import json
import os
import random
import sqlite3
import tkinter as tk
from abc import ABC, abstractmethod
from tkinter import filedialog, messagebox, simpledialog

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HIGHSCORE_FILE = os.path.join(BASE_DIR, "highscore.json")
DB_FILE = os.path.join(BASE_DIR, "scores.db")

SIZE = 4
CELL = 105
GAP = 5

TILE_COLORS = {
    0: "#f5f5f5",
    2: "#e0f2f8",
    4: "#b8dbe5",
    8: "#71b1bd",
    16: "#27819f",
    32: "#0073b9",
    64: "#7fa8d7",
    128: "#615ea6",
    256: "#2f3490",
    512: "#1c1862",
    1024: "#9c005d",
    2048: "#c80048",
}


class ScoreStorage(ABC):
    @abstractmethod
    def load_highscore(self) -> int: ...
    @abstractmethod
    def save_highscore(self, score: int) -> None: ...
    @abstractmethod
    def top_scores(self, limit: int = 5) -> list: ...
    @abstractmethod
    def describe(self) -> str: ...
    def close(self) -> None: pass


class JsonScoreStorage(ScoreStorage):
    def __init__(self, path: str):
        self.__path = path
    def load_highscore(self) -> int:
        try:
            with open(self.__path, "r") as f:
                return max(0, int(json.load(f).get("highscore", 0)))
        except Exception:
            return 0
    def save_highscore(self, score: int) -> None:
        try:
            with open(self.__path, "w") as f:
                json.dump({"highscore": int(score)}, f)
        except OSError:
            pass
    def top_scores(self, limit: int = 5) -> list:
        best = self.load_highscore()
        return [("Local record", best)] if best > 0 else []
    def describe(self) -> str:
        return "Storage: local JSON file"


class SqliteScoreStorage(ScoreStorage):
    def __init__(self, path: str, player: str):
        self.__player = player
        self.__conn = sqlite3.connect(path)
        self.__conn.execute(
            "CREATE TABLE IF NOT EXISTS highscores ("
            " player TEXT PRIMARY KEY,"
            " score INTEGER NOT NULL,"
            " updated_at TEXT NOT NULL)"
        )
        self.__conn.commit()
    def load_highscore(self) -> int:
        row = self.__conn.execute(
            "SELECT score FROM highscores WHERE player = ?", (self.__player,)
        ).fetchone()
        return int(row[0]) if row else 0
    def save_highscore(self, score: int) -> None:
        self.__conn.execute(
            "INSERT INTO highscores VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(player) DO UPDATE SET "
            " score = MAX(score, excluded.score), updated_at = datetime('now')",
            (self.__player, int(score)),
        )
        self.__conn.commit()
    def top_scores(self, limit: int = 5) -> list:
        rows = self.__conn.execute(
            "SELECT player, score FROM highscores ORDER BY score DESC LIMIT ?", (limit,)
        ).fetchall()
        return list(rows)
    def describe(self) -> str:
        return f"Storage: database (player: {self.__player})"
    def close(self) -> None:
        self.__conn.close()


class Tile:
    fg = "white"
    font_size = 36
    def __init__(self, value: int):
        self.value = value
    @property
    def bg(self) -> str:
        return TILE_COLORS.get(self.value, "#3c3a32")
    def label(self) -> str:
        return str(self.value) if self.value else ""
    def draw(self, canvas: tk.Canvas, x1, y1, x2, y2) -> None:
        canvas.create_rectangle(x1, y1, x2, y2, fill=self.bg, outline="")
        if self.value:
            canvas.create_text(
                (x1+x2)/2, (y1+y2)/2,
                font=("Arial", self.font_size), fill=self.fg, text=self.label()
            )

class EmptyTile(Tile):
    def draw(self, canvas, x1, y1, x2, y2) -> None:
        canvas.create_rectangle(x1, y1, x2, y2, fill=self.bg, outline="")

class LightTile(Tile): fg = "#494949"
class DarkTile(Tile): fg = "white"
class BigTile(DarkTile): font_size = 30
class HugeTile(DarkTile): font_size = 30

def tile_for(value: int) -> Tile:
    if value == 0: return EmptyTile(value)
    if value <= 4: return LightTile(value)
    if value <= 64: return DarkTile(value)
    if value <= 512: return BigTile(value)
    return HugeTile(value)


class Board:
    NEW_TILES = (2, 2, 2, 2, 2, 2, 4)
    WIN_VALUE = 2048
    def __init__(self):
        self.__cells = [[0]*SIZE for _ in range(SIZE)]
        self.__score = 0
        self.reset()
    @property
    def score(self) -> int:
        return self.__score
    def cell(self, row: int, col: int) -> int:
        return self.__cells[row][col]
    def reset(self) -> None:
        self.__cells = [[0]*SIZE for _ in range(SIZE)]
        self.__score = 0
        self.spawn_tile(); self.spawn_tile()
    def spawn_tile(self) -> bool:
        empty = [(r,c) for r in range(SIZE) for c in range(SIZE) if not self.__cells[r][c]]
        if not empty: return False
        r,c = random.choice(empty)
        self.__cells[r][c] = random.choice(self.NEW_TILES)
        return True
    def move(self, direction: str) -> bool:
        moved = False
        for line in self.__lines(direction):
            before = [self.__cells[r][c] for r,c in line]
            after, gained = self.__slide(before)
            if after != before:
                moved = True
                for (r,c),v in zip(line, after):
                    self.__cells[r][c] = v
                self.__score += gained
        if moved: self.spawn_tile()
        return moved
    def has_won(self) -> bool:
        return any(v >= self.WIN_VALUE for row in self.__cells for v in row)
    def is_over(self) -> bool:
        for r in range(SIZE):
            for c in range(SIZE):
                v = self.__cells[r][c]
                if v == 0: return False
                if c+1 < SIZE and self.__cells[r][c+1] == v: return False
                if r+1 < SIZE and self.__cells[r+1][c] == v: return False
        return True
    def to_dict(self) -> dict:
        return {"board": [row[:] for row in self.__cells], "score": self.__score}
    def load_dict(self, data: dict) -> None:
        cells, score = data["board"], data["score"]
        if not isinstance(score, int) or score < 0: raise ValueError("Invalid score")
        if len(cells) != SIZE: raise ValueError("Wrong board size")
        for row in cells:
            if len(row) != SIZE: raise ValueError("Wrong row size")
            for v in row:
                if v and (v < 2 or v & (v-1) != 0): raise ValueError("Bad tile value")
        self.__cells = [row[:] for row in cells]
        self.__score = score
    @staticmethod
    def __lines(d: str) -> list:
        R = range(SIZE)
        if d == "Left": return [[(r,c) for c in R] for r in R]
        if d == "Right": return [[(r,c) for c in reversed(R)] for r in R]
        if d == "Up": return [[(r,c) for r in R] for c in R]
        if d == "Down": return [[(r,c) for r in reversed(R)] for c in R]
        raise ValueError(d)
    @staticmethod
    def __slide(vals: list) -> tuple:
        tiles = [v for v in vals if v]
        merged, gained, i = [], 0, 0
        while i < len(tiles):
            if i+1 < len(tiles) and tiles[i] == tiles[i+1]:
                merged.append(tiles[i]*2)
                gained += tiles[i]*2
                i += 2
            else:
                merged.append(tiles[i]); i += 1
        merged += [0]*(len(vals)-len(merged))
        return merged, gained


class BoardView:
    def __init__(self, canvas: tk.Canvas):
        self.__canvas = canvas
    def render(self, board: Board, msg=None) -> None:
        self.__canvas.delete("all")
        if msg:
            self.__draw_msg(msg); return
        for r in range(SIZE):
            for c in range(SIZE):
                x,y = c*CELL, r*CELL
                tile_for(board.cell(r,c)).draw(
                    self.__canvas, x, y, x+CELL-GAP, y+CELL-GAP
                )
    def __draw_msg(self, words) -> None:
        for r in range(SIZE):
            word = words[r] if r < len(words) else ""
            for c in range(SIZE):
                x,y = c*CELL, r*CELL
                self.__canvas.create_rectangle(x, y, x+CELL-GAP, y+CELL-GAP, fill="#e0f2f8", outline="")
                if c < len(word) and word[c] != " ":
                    self.__canvas.create_text((x+x+CELL-GAP)/2, (y+y+CELL-GAP)/2,
                        font=("Arial",36), fill="#494949", text=word[c])


class Game(tk.Tk):
    PLAYING, WON, OVER = "playing", "won", "over"
    def __init__(self):
        super().__init__()
        
        # ==============================================
        # ✅ BAGONG BACKGROUND NA KULAY — PALITAN MO ITO
        # ==============================================
        self.configure(bg="#50157a")  # Kulay ng buong bintana

        self.board = Board()
        self.storage: ScoreStorage = JsonScoreStorage(HIGHSCORE_FILE)
        self.highscore = self.storage.load_highscore()
        self.status = self.PLAYING
        self.scorestring = tk.StringVar(self, "0")
        self.highscorestring = tk.StringVar(self, str(self.highscore))
        self.modestring = tk.StringVar(self, self.storage.describe())
        
        self._build_menu()
        self._build_widgets()
        self.view = BoardView(self.canvas)
        
        self.bind_all("<Key>", self._on_key)
        self.bind_all("<Control-n>", lambda _: self.new_game())
        self.bind_all("<Control-s>", lambda _: self._save())
        self.bind_all("<Control-o>", lambda _: self._load())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self._refresh()

    def _build_menu(self):
        mb = tk.Menu(self)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="New Game", accelerator="Ctrl+N", command=self.new_game)
        fm.add_command(label="Save Game", accelerator="Ctrl+S", command=self._save)
        fm.add_command(label="Load Game", accelerator="Ctrl+O", command=self._load)
        fm.add_separator(); fm.add_command(label="Exit", command=self._on_close)
        mb.add_cascade(label="File", menu=fm)
        
        self.conn_menu = tk.Menu(mb, tearoff=0)
        self.conn_menu.add_command(label="Connect to Database...", command=self._connect_db)
        self.conn_menu.add_command(label="Disconnect", command=self._disconnect, state="disabled")
        self.conn_menu.add_separator()
        self.conn_menu.add_command(label="Leaderboard", command=self._leaderboard)
        mb.add_cascade(label="Connect", menu=self.conn_menu)
        
        self.config(menu=mb)

    def _build_widgets(self):
        bar = tk.Frame(self, bg="#0808ec")
        tk.Button(bar, text="New Game", command=self.new_game, bg="#b62de3", fg="white").grid(row=0,column=0, padx=3)
        tk.Label(bar, text="Score:", bg="#0f0fe3", fg="white").grid(row=0,column=1)
        tk.Label(bar, textvariable=self.scorestring, bg="#0808ec", fg="white").grid(row=0,column=2)
        tk.Label(bar, text="Record:", bg="#0808ec", fg="white").grid(row=0,column=3)
        tk.Label(bar, textvariable=self.highscorestring, bg="#0808ec", fg="white").grid(row=0,column=4)
        bar.pack(side="top")
        
        tk.Label(self, textvariable=self.modestring, fg="#a0a0a0", bg="#50ea6b").pack(side="top")
        
        # ✅ Kulay ng laro board
        self.canvas = tk.Canvas(self, width=420, height=420, 
                                bg="#50157a", borderwidth=6, highlightthickness=0)
        self.canvas.pack(side="top", expand=True)

    def _refresh(self):
        msg = ("YOU","WON!") if self.status==self.WON else ("GAME","OVER") if self.status==self.OVER else None
        self.view.render(self.board, msg)
        self.scorestring.set(str(self.board.score))
        self.highscorestring.set(str(self.highscore))
        self.modestring.set(self.storage.describe())

    def _sync_status(self):
        if self.board.has_won(): self.status = self.WON
        elif self.board.is_over(): self.status = self.OVER
        else: self.status = self.PLAYING

    def _update_highscore(self):
        if self.board.score > self.highscore:
            self.highscore = self.board.score
            try: self.storage.save_highscore(self.highscore)
            except sqlite3.Error:
                messagebox.showwarning("DB Error", "Falling back to local file")
                self._disconnect()

    def _on_key(self, e):
        if self.grab_current(): return
        if e.keysym not in ("Up","Down","Left","Right"): return
        if self.status != self.PLAYING: return
        if self.board.move(e.keysym):
            self._update_highscore(); self._sync_status(); self._refresh()

    def new_game(self):
        self.board.reset(); self.status=self.PLAYING; self._refresh()

    def _save(self):
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if not path: return
        with open(path,"w") as f: json.dump(self.board.to_dict(), f)

    def _load(self):
        path = filedialog.askopenfilename(filetypes=[("JSON","*.json")])
        if not path: return
        try:
            with open(path) as f: self.board.load_dict(json.load(f))
            self._sync_status(); self._update_highscore(); self._refresh()
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def _connect_db(self):
        player = simpledialog.askstring("Player", "Your name:")
        if not player: return
        try:
            new_storage = SqliteScoreStorage(DB_FILE, player.strip())
            self.storage.close()
            self.storage = new_storage
            self.highscore = self.storage.load_highscore()
            self.conn_menu.entryconfig("Connect to Database...", state="disabled")
            self.conn_menu.entryconfig("Disconnect", state="normal")
            self._refresh()
        except Exception as e:
            messagebox.showerror("Connection failed", str(e))

    def _disconnect(self):
        self.storage.close()
        self.storage = JsonScoreStorage(HIGHSCORE_FILE)
        self.highscore = self.storage.load_highscore()
        self.conn_menu.entryconfig("Connect to Database...", state="normal")
        self.conn_menu.entryconfig("Disconnect", state="disabled")
        self._refresh()

    def _leaderboard(self):
        scores = self.storage.top_scores(5)
        body = "\n".join(f"{i+1}. {n} - {s}" for i,(n,s) in enumerate(scores)) or "No scores yet."
        messagebox.showinfo("Leaderboard", f"{self.storage.describe()}\n\n{body}")

    def _on_close(self):
        if self.highscore > 0:
            try: self.storage.save_highscore(self.highscore)
            except Exception: pass
        self.storage.close()
        self.destroy()


if __name__ == "__main__":
    app = Game()
    app.title("Fusion Number")
    app.minsize(680, 450)
    app.mainloop()