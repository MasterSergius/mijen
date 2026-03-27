from nicegui import ui
from mijen.ui.theme import frame


def content():
    with frame("System Setup"):
        ui.label("MiJen Settings").classes("text-h4 mb-6")

        with ui.column().classes("gap-4 w-full max-w-2xl"):
            ui.select(["English", "Ukrainian", "Spanish"], label="Language").classes(
                "w-full"
            )
            ui.select(["Light", "Dark", "System"], label="Theme").classes("w-full")
            ui.input("Logs Directory", value="./logs").classes("w-full")

            ui.button("Save System Config", color="primary").classes("w-full")
