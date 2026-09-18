"""Toggle a QPushButton between its normal state and a spinning "busy"
state - swaps in a rotating spinner icon and disables the button so it
can't be double-submitted while a request (e.g. a sign-in check) is in
flight. The original text/icon are stashed on the button itself and
restored exactly when loading ends.
"""
import qtawesome as qta
from PySide6.QtWidgets import QPushButton


def set_button_loading(button: QPushButton, loading: bool, busy_text: str = "Please wait..."):
    if loading:
        if not hasattr(button, "_idle_text"):
            button._idle_text = button.text()
            button._idle_icon = button.icon()
        button.setEnabled(False)
        button.setText(f"  {busy_text}")
        spin = qta.Spin(button, interval=10, step=4)
        button.setIcon(qta.icon("fa5s.spinner", color="white", animation=spin))
    else:
        button.setEnabled(True)
        if hasattr(button, "_idle_text"):
            button.setText(button._idle_text)
            button.setIcon(button._idle_icon)
