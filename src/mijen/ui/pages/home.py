from nicegui import ui
from mijen.ui.theme import frame


def content():
    with frame("Welcome"):
        ui.markdown("""
        # Welcome to MiJen 🚀
        MiJen is a lightweight, educational CI/CD automation server. 
        
        ### Quick Guide:
        1. Go to **Projects** to see existing work.
        2. Create a **New Project** to link a Git repository.
        3. Define **Tasks** (like "Run Tests" or "Lint Code") for your project.
        """)

        ui.button(
            "Add New Project",
            icon="add",
            on_click=lambda: ui.navigate.to("/projects/create"),
        ).classes("mt-4")
