"""Small reusable animation helpers used to keep transitions consistent
across the app - a soft crossfade when a QStackedWidget's page changes, and
a staggered fade+rise entrance for groups of widgets (dashboard cards etc).
"""
from PySide6.QtCore import QPoint, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect

# Keep strong references to in-flight animations so they aren't garbage
# collected mid-flight (Qt only keeps them alive via the object tree, which
# isn't enough once the parent widget itself gets a fresh graphics effect).
_live = []


def crossfade_stack(stack, new_widget, duration: int = 260):
    """Switch a QStackedWidget's current page with a soft crossfade instead
    of an instant cut, so navigation feels continuous rather than jarring."""
    if stack.currentWidget() is new_widget:
        return
    stack.setCurrentWidget(new_widget)

    effect = QGraphicsOpacityEffect(new_widget)
    new_widget.setGraphicsEffect(effect)
    effect.setOpacity(0.0)

    anim = QPropertyAnimation(effect, b"opacity", new_widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _cleanup():
        new_widget.setGraphicsEffect(None)
        if anim in _live:
            _live.remove(anim)

    anim.finished.connect(_cleanup)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
    _live.append(anim)


def fade_slide_in(widget, delay: int = 0, duration: int = 420, dy: int = 18):
    """Fade + gently rise a widget into its resting position - used for a
    staggered entrance across a group of widgets (e.g. dashboard cards) so
    the page feels alive without being distracting."""

    def _start():
        if not widget.isVisible():
            return
        rest_pos = widget.pos()
        start_pos = QPoint(rest_pos.x(), rest_pos.y() + dy)

        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        widget.move(start_pos)

        fade = QPropertyAnimation(effect, b"opacity", widget)
        fade.setDuration(duration)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)

        move = QPropertyAnimation(widget, b"pos", widget)
        move.setDuration(duration)
        move.setStartValue(start_pos)
        move.setEndValue(rest_pos)
        move.setEasingCurve(QEasingCurve.Type.OutCubic)

        group = QParallelAnimationGroup(widget)
        group.addAnimation(fade)
        group.addAnimation(move)

        def _cleanup():
            widget.setGraphicsEffect(None)
            if group in _live:
                _live.remove(group)

        group.finished.connect(_cleanup)
        group.start(QParallelAnimationGroup.DeletionPolicy.DeleteWhenStopped)
        _live.append(group)

    QTimer.singleShot(delay, _start)
