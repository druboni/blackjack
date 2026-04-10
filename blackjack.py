#!/usr/bin/env python3
"""
Blackjack — cross-platform (Windows, macOS, Linux)
Requires: Python 3.8+ with tkinter (included in standard Python installs)
Optional: pip install pygame  (enables sound effects)
"""

import tkinter as tk
from tkinter import font as tkfont
import random
import io
import wave
import struct
import math
import sys
import threading
import subprocess


# ── Sound engine ───────────────────────────────────────────

class Sounds:
    """
    Generates tones from pure Python math — no sound files, no extra installs.
    Plays via winsound (Windows), afplay (macOS), or aplay (Linux).
    """
    RATE = 22050

    def __init__(self):
        self._lib = {}
        try:
            self._lib = {
                "deal":      self._tone(600,  0.08),
                "hit":       self._tone(480,  0.08),
                "win":       self._seq([(523, 0.12), (659, 0.12), (784, 0.22)]),
                "blackjack": self._seq([(523, 0.09), (659, 0.09), (784, 0.09), (1047, 0.32)]),
                "lose":      self._seq([(330, 0.18), (247, 0.32)]),
                "bust":      self._tone(140,  0.38),
                "push":      self._tone(440,  0.25),
            }
        except Exception:
            pass

    def play(self, name):
        wav = self._lib.get(name)
        if wav:
            threading.Thread(target=self._play, args=(wav,), daemon=True).start()

    def _play(self, wav_bytes):
        try:
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
            elif sys.platform == "darwin":
                import tempfile, os
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(wav_bytes); path = f.name
                subprocess.run(["afplay", path], capture_output=True)
                os.unlink(path)
            else:
                import tempfile, os
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(wav_bytes); path = f.name
                subprocess.run(["aplay", "-q", path], capture_output=True)
                os.unlink(path)
        except Exception:
            pass

    def _pcm(self, freq, duration, volume=0.4):
        n = int(self.RATE * duration)
        return struct.pack(
            "<" + "h" * n,
            *[int(32767 * volume
                  * math.sin(2 * math.pi * freq * i / self.RATE)
                  * max(0.0, 1 - i / n))
              for i in range(n)]
        )

    def _wav(self, pcm):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(self.RATE)
            w.writeframes(pcm)
        return buf.getvalue()

    def _tone(self, freq, duration, volume=0.4):
        return self._wav(self._pcm(freq, duration, volume))

    def _seq(self, notes, volume=0.4):
        return self._wav(b"".join(self._pcm(f, d, volume) for f, d in notes))

# ── Constants ──────────────────────────────────────────────
SUITS     = ["♠", "♥", "♦", "♣"]
RANKS     = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
RED_SUITS = {"♥", "♦"}

CARD_W    = 80
CARD_H    = 110
PAD       = 16

BG        = "#076324"
FACE_F    = "#ffffff"
FACE_O    = "#888888"
BACK_F    = "#1a237e"
BACK_O    = "#3949ab"
RED_C     = "#cc0000"
BLACK_C   = "#111111"
GOLD      = "#ffd700"
BTN_BG    = "#1b5e20"
BTN_FG    = "#ffffff"
BTN_ACT   = "#2e7d32"

STARTING_CHIPS = 1000
DEFAULT_BET    = 50


# ── Card / Deck ────────────────────────────────────────────

class Card:
    def __init__(self, suit, rank, hidden=False):
        self.suit   = suit
        self.rank   = rank
        self.hidden = hidden

    @property
    def value(self):
        if self.rank in ("J", "Q", "K"):
            return 10
        if self.rank == "A":
            return 11   # aces handled in hand_value()
        return int(self.rank)

    @property
    def is_red(self):
        return self.suit in RED_SUITS


def hand_value(hand):
    """Return best value of a hand (accounts for soft aces)."""
    total = sum(c.value for c in hand if not c.hidden)
    aces  = sum(1 for c in hand if c.rank == "A" and not c.hidden)
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total


def new_deck():
    deck = [Card(s, r) for s in SUITS for r in RANKS] * 6
    random.shuffle(deck)
    return deck


# ── Game logic ─────────────────────────────────────────────

class BlackjackGame:
    def __init__(self):
        self.chips   = STARTING_CHIPS
        self.bet     = DEFAULT_BET
        self.deck    = new_deck()
        self.player  = []
        self.dealer  = []
        self.state   = "betting"   # betting | playing | dealer | done

    def _deal(self, hidden=False):
        if len(self.deck) < 20:
            self.deck = new_deck()
        c = self.deck.pop()
        c.hidden = hidden
        return c

    def start_round(self, bet):
        self.bet    = bet
        self.chips -= bet
        self.player = [self._deal(), self._deal()]
        self.dealer = [self._deal(), self._deal(hidden=True)]
        self.state  = "playing"
        # Natural blackjack?
        if hand_value(self.player) == 21:
            self._reveal_dealer()
            self.state = "done"

    def hit(self):
        self.player.append(self._deal())
        if hand_value(self.player) >= 21:
            self._reveal_dealer()
            self.state = "done"

    def stand(self):
        self._reveal_dealer()
        self._dealer_play()
        self.state = "done"

    def double_down(self):
        self.chips -= self.bet
        self.bet   *= 2
        self.player.append(self._deal())
        self._reveal_dealer()
        if hand_value(self.player) <= 21:
            self._dealer_play()
        self.state = "done"

    def _reveal_dealer(self):
        for c in self.dealer:
            c.hidden = False

    def _dealer_play(self):
        while hand_value(self.dealer) < 17:
            self.dealer.append(self._deal())

    def result(self):
        """Return (message, winnings) after round ends."""
        pv = hand_value(self.player)
        dv = hand_value(self.dealer)
        p_bj = pv == 21 and len(self.player) == 2
        d_bj = dv == 21 and len(self.dealer) == 2

        if p_bj and d_bj:
            self.chips += self.bet
            return "Push — both Blackjack!", 0
        if p_bj:
            win = int(self.bet * 1.5)
            self.chips += self.bet + win
            return f"Blackjack! +{win}", win
        if d_bj:
            return f"Dealer Blackjack. -{self.bet}", -self.bet
        if pv > 21:
            return f"Bust! -{self.bet}", -self.bet
        if dv > 21:
            self.chips += self.bet * 2
            return f"Dealer busts! +{self.bet}", self.bet
        if pv > dv:
            self.chips += self.bet * 2
            return f"You win! +{self.bet}", self.bet
        if dv > pv:
            return f"Dealer wins. -{self.bet}", -self.bet
        self.chips += self.bet
        return "Push!", 0

    def can_double(self):
        return len(self.player) == 2 and self.chips >= self.bet


# ── UI ─────────────────────────────────────────────────────

class BlackjackApp:
    def __init__(self, root: tk.Tk):
        self.root   = root
        self.game   = BlackjackGame()
        self.sounds = Sounds()

        root.title("Blackjack")
        root.configure(bg=BG)
        root.resizable(False, False)

        # Bind quit
        root.bind("<Control-q>", lambda e: root.quit())
        root.bind("<Command-q>", lambda e: root.quit())  # macOS

        self._build_ui()
        self._update()

    # ── Build UI ───────────────────────────────────────────

    def _build_ui(self):
        g = self.game

        # Canvas for cards
        self.canvas = tk.Canvas(
            self.root, width=600, height=340,
            bg=BG, highlightthickness=0
        )
        self.canvas.pack(padx=PAD, pady=(PAD, 0))

        # Status label
        self.status_var = tk.StringVar(value="Place your bet to start.")
        self.status_lbl = tk.Label(
            self.root, textvariable=self.status_var,
            bg=BG, fg=GOLD, font=("Helvetica", 14, "bold")
        )
        self.status_lbl.pack(pady=(8, 0))

        # Chips & bet row
        info_frame = tk.Frame(self.root, bg=BG)
        info_frame.pack(pady=4)

        tk.Label(info_frame, text="Chips:", bg=BG, fg="white",
                 font=("Helvetica", 12)).pack(side="left", padx=4)
        self.chips_var = tk.StringVar()
        tk.Label(info_frame, textvariable=self.chips_var,
                 bg=BG, fg=GOLD, font=("Helvetica", 12, "bold"),
                 width=6, anchor="w").pack(side="left")

        tk.Label(info_frame, text="Bet:", bg=BG, fg="white",
                 font=("Helvetica", 12)).pack(side="left", padx=(16, 4))
        self.bet_var = tk.IntVar(value=DEFAULT_BET)
        self.bet_spin = tk.Spinbox(
            info_frame, from_=10, to=500, increment=10,
            textvariable=self.bet_var, width=6,
            font=("Helvetica", 12), state="normal"
        )
        self.bet_spin.pack(side="left")

        # Action buttons
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(pady=(6, PAD))

        def btn(text, cmd, var=None):
            b = tk.Button(
                btn_frame, text=text, command=cmd,
                bg=BTN_BG, fg=BTN_FG, activebackground=BTN_ACT,
                activeforeground=BTN_FG, relief="flat",
                font=("Helvetica", 12, "bold"),
                padx=14, pady=6, cursor="hand2"
            )
            b.pack(side="left", padx=6)
            if var is not None:
                var.append(b)
            return b

        self.btn_deal   = btn("Deal",        self._deal)
        self.btn_hit    = btn("Hit",         self._hit)
        self.btn_stand  = btn("Stand",       self._stand)
        self.btn_double = btn("Double Down", self._double)
        self.btn_quit   = btn("Quit",        self.root.quit)

    # ── Actions ────────────────────────────────────────────

    def _deal(self):
        bet = self.bet_var.get()
        if bet > self.game.chips:
            self.status_var.set("Not enough chips!")
            return
        self.sounds.play("deal")
        self.game.start_round(bet)
        self._update()
        if self.game.state == "done":
            self._finish()

    def _hit(self):
        self.sounds.play("hit")
        self.game.hit()
        self._update()
        if self.game.state == "done":
            self._finish()

    def _stand(self):
        self.game.stand()
        self._update()
        self._finish()

    def _double(self):
        self.sounds.play("hit")
        self.game.double_down()
        self._update()
        self._finish()

    def _finish(self):
        msg, amount = self.game.result()
        # Play result sound
        if "Blackjack" in msg and amount > 0:
            self.sounds.play("blackjack")
        elif "Bust" in msg and amount < 0:
            self.sounds.play("bust")
        elif amount > 0:
            self.sounds.play("win")
        elif amount < 0:
            self.sounds.play("lose")
        else:
            self.sounds.play("push")
        self.status_var.set(msg)
        self._update()
        if self.game.chips <= 0:
            self.status_var.set("Out of chips! Starting over.")
            self.game.chips = STARTING_CHIPS
        self.game.state = "betting"
        self._update_buttons()

    # ── Draw ───────────────────────────────────────────────

    def _update(self):
        self._draw_table()
        self._update_buttons()
        self.chips_var.set(f"${self.game.chips}")

    def _update_buttons(self):
        s = self.game.state
        self.btn_deal  .config(state="normal"   if s == "betting" else "disabled")
        self.bet_spin  .config(state="normal"   if s == "betting" else "disabled")
        self.btn_hit   .config(state="normal"   if s == "playing" else "disabled")
        self.btn_stand .config(state="normal"   if s == "playing" else "disabled")
        self.btn_double.config(
            state="normal" if s == "playing" and self.game.can_double() else "disabled"
        )

    def _draw_table(self):
        cv = self.canvas
        cv.delete("all")

        # Labels
        cv.create_text(10, 10, text="Dealer", fill="white",
                       font=("Helvetica", 11, "bold"), anchor="nw")
        cv.create_text(10, 180, text="You", fill="white",
                       font=("Helvetica", 11, "bold"), anchor="nw")

        # Dealer score (hide if hole card still hidden)
        dealer_visible = [c for c in self.game.dealer if not c.hidden]
        if dealer_visible:
            dv = hand_value(dealer_visible)
            cv.create_text(70, 10, text=f"  {dv}", fill=GOLD,
                           font=("Helvetica", 11, "bold"), anchor="nw")

        # Player score
        if self.game.player:
            pv = hand_value(self.game.player)
            label = str(pv)
            if pv > 21:
                label += " BUST"
            cv.create_text(40, 180, text=f"  {label}", fill=GOLD,
                           font=("Helvetica", 11, "bold"), anchor="nw")

        # Draw hands
        self._draw_hand(self.game.dealer, start_x=10, y=30)
        self._draw_hand(self.game.player, start_x=10, y=200)

    def _draw_hand(self, hand, start_x, y):
        cv  = self.canvas
        x   = start_x
        gap = CARD_W + 8

        for card in hand:
            if card.hidden:
                # Card back
                cv.create_rectangle(x, y, x+CARD_W, y+CARD_H,
                                    fill=BACK_F, outline=BACK_O, width=2)
                cv.create_rectangle(x+6, y+6, x+CARD_W-6, y+CARD_H-6,
                                    fill=BACK_F, outline="#5c6bc0", width=1)
            else:
                clr = RED_C if card.is_red else BLACK_C
                cv.create_rectangle(x, y, x+CARD_W, y+CARD_H,
                                    fill=FACE_F, outline=FACE_O, width=1)
                # Top-left
                cv.create_text(x+5, y+6, text=card.rank, fill=clr,
                               font=("Helvetica", 11, "bold"), anchor="nw")
                cv.create_text(x+5, y+20, text=card.suit, fill=clr,
                               font=("Helvetica", 10), anchor="nw")
                # Center
                cv.create_text(x+CARD_W//2, y+CARD_H//2,
                               text=card.suit, fill=clr,
                               font=("Helvetica", 28))
                # Bottom-right
                cv.create_text(x+CARD_W-5, y+CARD_H-6,
                               text=card.rank, fill=clr,
                               font=("Helvetica", 11, "bold"), anchor="se")
                cv.create_text(x+CARD_W-5, y+CARD_H-20,
                               text=card.suit, fill=clr,
                               font=("Helvetica", 10), anchor="se")
            x += gap


def main():
    root = tk.Tk()
    BlackjackApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
