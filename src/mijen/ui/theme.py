from contextlib import contextmanager
from nicegui import ui


@contextmanager
def frame(nav_title: str, custom_sidebar=None):
    ui.colors(primary="#1e293b", secondary="#64748b")

    with ui.header().classes("justify-between items-center bg-slate-800"):
        ui.label("MiJen").classes("font-bold text-lg cursor-pointer").on(
            "click", lambda: ui.navigate.to("/")
        )
        ui.label(nav_title).classes("text-sm uppercase tracking-widest opacity-70")

    with ui.left_drawer().classes("bg-slate-50 border-r"):
        if custom_sidebar:
            custom_sidebar()  # Run the specific sidebar logic
        else:
            # Default Global Sidebar
            ui.label("GLOBAL").classes("text-xs font-bold p-4 text-slate-400")
            ui.button("Home", icon="home", on_click=lambda: ui.navigate.to("/")).props(
                "flat"
            ).classes("w-full justify-start")
            ui.button(
                "Projects", icon="list", on_click=lambda: ui.navigate.to("/projects")
            ).props("flat").classes("w-full justify-start")
            ui.button(
                "App Setup", icon="settings", on_click=lambda: ui.navigate.to("/setup")
            ).props("flat").classes("w-full justify-start")

    with ui.column().classes("w-full p-8"):
        yield
