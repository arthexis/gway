"""Interactive helpers for creating and previewing game content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from gway import gw


@dataclass(slots=True)
class _CookbookState:
    """Keep track of cookbook navigation state."""

    folders: list[Path]
    folder_index: int = 0
    recipe_index: int = 0
    focus: str = "folders"

    def current_folder(self) -> Path:
        return self.folders[self.folder_index]

    def recipes(self) -> list[Path]:
        folder = self.current_folder()
        recipe_files = sorted(folder.glob("*.gwr"))
        return recipe_files

    def current_recipe(self) -> Path | None:
        recipes = self.recipes()
        if not recipes:
            return None
        if self.recipe_index >= len(recipes):
            self.recipe_index = max(0, len(recipes) - 1)
        return recipes[self.recipe_index]

    def move_folder(self, delta: int) -> None:
        self.folder_index = (self.folder_index + delta) % len(self.folders)
        self.recipe_index = 0

    def move_recipe(self, delta: int) -> None:
        recipes = self.recipes()
        if not recipes:
            self.recipe_index = 0
            return
        self.recipe_index = (self.recipe_index + delta) % len(recipes)


def _collect_recipe_folders(root: Path) -> list[Path]:
    folders = [root]
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        folders.append(sub)
    return folders


def _wrap_text(text: str, width: int, font) -> Iterable[object]:
    import textwrap

    for paragraph in text.splitlines() or [""]:
        if not paragraph.strip():
            yield font.render("", True, (230, 230, 230))
            continue
        for line in textwrap.wrap(paragraph, width=width):
            yield font.render(line, True, (230, 230, 230))


def open_cookbook(
    *,
    recipes_root: str | Path | None = None,
    window_size: tuple[int, int] = (960, 640),
    frame_rate: int = 30,
) -> dict[str, object]:
    """Launch a pygame viewer for browsing Gateway recipe files.

    Parameters
    ----------
    recipes_root:
        Directory containing ``.gwr`` recipe files. Defaults to the built-in
        ``recipes`` resource.
    window_size:
        Size of the pygame window in pixels.
    frame_rate:
        Target frames per second for the draw loop.

    Returns
    -------
    dict
        Summary of the last selected folder and recipe when the window closes.
    """

    if not gw.interactive_enabled:
        raise RuntimeError("open_cookbook requires interactive mode. Run with `-i`.")

    try:
        import pygame
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "open_cookbook requires the 'pygame' package. Install it with `pip install pygame`."
        ) from exc

    recipe_root_path = Path(recipes_root) if recipes_root is not None else gw.resource("recipes")
    recipe_root_path = recipe_root_path.expanduser().resolve()

    if not recipe_root_path.exists():
        raise FileNotFoundError(f"Recipe directory {recipe_root_path} does not exist.")

    folders = _collect_recipe_folders(recipe_root_path)
    if not folders:
        raise RuntimeError(f"No recipe folders found inside {recipe_root_path}.")

    pygame.init()
    screen = pygame.display.set_mode(window_size)
    pygame.display.set_caption("Gateway Cookbook")
    clock = pygame.time.Clock()

    header_font = pygame.font.SysFont("arial", 28)
    body_font = pygame.font.SysFont("consolas", 20)

    state = _CookbookState(folders=folders)
    running = True
    visited: set[Path] = set()

    panel_bg = (24, 32, 48)
    highlight = (70, 120, 190)
    background = (12, 16, 26)
    text_color = (230, 230, 230)

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_TAB, pygame.K_LEFT, pygame.K_RIGHT):
                    state.focus = "recipes" if state.focus == "folders" else "folders"
                elif event.key == pygame.K_UP:
                    if state.focus == "folders":
                        state.move_folder(-1)
                    else:
                        state.move_recipe(-1)
                elif event.key == pygame.K_DOWN:
                    if state.focus == "folders":
                        state.move_folder(1)
                    else:
                        state.move_recipe(1)

        screen.fill(background)

        folder_panel = pygame.Rect(20, 60, 260, window_size[1] - 80)
        recipe_panel = pygame.Rect(300, 60, 280, window_size[1] - 80)
        preview_panel = pygame.Rect(600, 60, window_size[0] - 620, window_size[1] - 80)

        pygame.draw.rect(screen, panel_bg, folder_panel, border_radius=8)
        pygame.draw.rect(screen, panel_bg, recipe_panel, border_radius=8)
        pygame.draw.rect(screen, panel_bg, preview_panel, border_radius=8)

        title_surface = header_font.render("Gateway Cookbook", True, text_color)
        screen.blit(title_surface, (20, 16))

        folder_title = body_font.render("Folders", True, text_color)
        screen.blit(folder_title, (folder_panel.x + 16, folder_panel.y + 10))
        recipe_title = body_font.render("Recipes", True, text_color)
        screen.blit(recipe_title, (recipe_panel.x + 16, recipe_panel.y + 10))
        preview_title = body_font.render("Preview", True, text_color)
        screen.blit(preview_title, (preview_panel.x + 16, preview_panel.y + 10))

        folder_y = folder_panel.y + 50
        for index, folder in enumerate(state.folders):
            label = folder.name or folder.as_posix()
            if index == 0 and folder == recipe_root_path:
                label = "(root)" if folder.name == "" else folder.name
            surface = body_font.render(label, True, text_color)
            row_rect = pygame.Rect(folder_panel.x + 8, folder_y - 4, folder_panel.width - 16, surface.get_height() + 8)
            if index == state.folder_index:
                pygame.draw.rect(screen, highlight, row_rect, border_radius=6)
            screen.blit(surface, (folder_panel.x + 16, folder_y))
            folder_y += surface.get_height() + 10

        recipe_y = recipe_panel.y + 50
        recipes = state.recipes()
        if recipes:
            for index, recipe in enumerate(recipes):
                surface = body_font.render(recipe.stem, True, text_color)
                row_rect = pygame.Rect(recipe_panel.x + 8, recipe_y - 4, recipe_panel.width - 16, surface.get_height() + 8)
                if index == state.recipe_index:
                    pygame.draw.rect(screen, highlight, row_rect, border_radius=6)
                    visited.add(recipe)
                screen.blit(surface, (recipe_panel.x + 16, recipe_y))
                recipe_y += surface.get_height() + 10
        else:
            empty_surface = body_font.render("(no recipes)", True, text_color)
            screen.blit(empty_surface, (recipe_panel.x + 16, recipe_y))

        preview_recipe = state.current_recipe()
        if preview_recipe and preview_recipe.exists():
            try:
                content = preview_recipe.read_text(encoding="utf-8")
            except Exception as exc:  # pragma: no cover - file IO
                content = f"Unable to read recipe: {exc}"
        else:
            content = "Select a recipe to preview its contents."

        preview_text_y = preview_panel.y + 50
        wrap_width = max(10, (preview_panel.width - 32) // 10)
        for line_surface in _wrap_text(content, wrap_width, body_font):
            screen.blit(line_surface, (preview_panel.x + 16, preview_text_y))
            preview_text_y += line_surface.get_height() + 4
            if preview_text_y > preview_panel.bottom - 16:
                break

        pygame.display.flip()
        clock.tick(frame_rate)

    selected_recipe = state.current_recipe()
    pygame.quit()

    return {
        "recipes_root": str(recipe_root_path),
        "selected_folder": str(state.current_folder()),
        "selected_recipe": str(selected_recipe) if selected_recipe else None,
        "recipes_viewed": [str(path) for path in sorted(visited)],
    }


def dashboard(
    *,
    project: str | object,
    window_size: tuple[int, int] = (960, 640),
    frame_rate: int = 30,
) -> dict[str, object]:
    """Display a pygame dashboard for invoking project functions.

    Parameters
    ----------
    project:
        Gateway project name or project object exposing callable utilities.
    window_size:
        Size of the pygame window in pixels.
    frame_rate:
        Target frames per second for the draw loop.

    Returns
    -------
    dict
        Summary of executed functions and their latest results.
    """

    if not gw.interactive_enabled:
        raise RuntimeError("dashboard requires interactive mode. Run with `-i`.")

    try:
        import pygame
    except ImportError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "dashboard requires the 'pygame' package. Install it with `pip install pygame`."
        ) from exc

    project_obj: object
    project_name: str
    if isinstance(project, str):
        if not project.strip():
            raise ValueError("Project name cannot be empty.")
        try:
            project_obj = getattr(gw, project)
        except AttributeError as exc:
            raise ValueError(f"Gateway has no project named '{project}'.") from exc
        project_name = project
    else:
        project_obj = project
        project_name = getattr(project_obj, "_name", None) or getattr(
            project_obj, "__name__", project_obj.__class__.__name__
        )

    def discover_functions(target: object) -> list[tuple[str, Callable[[], Any]]]:
        functions: list[tuple[str, Callable[[], Any]]] = []

        candidate_names: set[str] = set()
        for name in (project_name, getattr(target, "_name", None), getattr(target, "__name__", None)):
            if not name:
                continue
            candidate_names.add(name)
            candidate_names.add(name.rsplit(".", 1)[-1])

        module_prefixes: set[str] = set()
        for name in candidate_names:
            module_prefixes.add(name)
            module_prefixes.add(name.replace(".", "_"))
            if not name.startswith("projects."):
                module_prefixes.add(f"projects.{name}")

        def matches_project(module_name: str) -> bool:
            if not module_name:
                return False
            for prefix in module_prefixes:
                if module_name == prefix:
                    return True
                if module_name.startswith(prefix + "."):
                    return True
                if module_name.endswith(f".{prefix}"):
                    return True
            return False

        for attr_name in sorted(dir(target)):
            if attr_name.startswith("_"):
                continue
            try:
                attr = getattr(target, attr_name)
            except AttributeError:
                continue
            if not callable(attr):
                continue
            module_name = getattr(attr, "__module__", "")
            if module_prefixes and not matches_project(module_name):
                continue
            functions.append((attr_name, attr))
        return functions

    functions = discover_functions(project_obj)
    if not functions:
        raise RuntimeError(f"No callable functions found for project '{project_name}'.")

    pygame.init()
    min_width, min_height = 640, 480
    initial_width = max(window_size[0], min_width)
    initial_height = max(window_size[1], min_height)
    screen = pygame.display.set_mode((initial_width, initial_height), pygame.RESIZABLE)
    pygame.display.set_caption(f"Gateway {project_name} Dashboard")
    clock = pygame.time.Clock()

    title_font = pygame.font.SysFont("arial", 28)
    button_font = pygame.font.SysFont("arial", 20)
    log_font = pygame.font.SysFont("consolas", 18)

    background = (12, 16, 26)
    panel_bg = (24, 32, 48)
    button_bg = (56, 80, 120)
    button_hover = (80, 120, 170)
    text_color = (230, 230, 230)
    error_color = (220, 110, 110)

    button_spacing = 12
    scroll_offset = 0
    call_history: list[dict[str, Any]] = []
    log_lines: list[tuple[str, bool]] = []

    instructions_text = "Click a function to execute (Esc to close)"

    def compute_layout(current_size: tuple[int, int]) -> dict[str, Any]:
        width, height = current_size
        button_width = max(260, int(width * 0.32))
        panel_height = max(220, height - 80)
        button_rect = pygame.Rect(20, 60, button_width, panel_height)
        log_width = max(240, width - button_rect.width - 60)
        log_rect = pygame.Rect(button_rect.right + 20, 60, log_width, panel_height)
        instructions_height = button_font.size(instructions_text)[1]
        list_top = button_rect.y + 16 + instructions_height + 12
        list_bottom = button_rect.bottom - 20
        visible_height = max(0, list_bottom - list_top)
        log_text_top = log_rect.y + 50
        log_text_bottom = log_rect.bottom - 20
        log_visible_height = max(0, log_text_bottom - log_text_top)
        button_text_width = max(20, button_rect.width - 32)
        return {
            "button_panel": button_rect,
            "log_panel": log_rect,
            "button_list_top": list_top,
            "button_list_bottom": list_bottom,
            "button_visible_height": visible_height,
            "log_text_top": log_text_top,
            "log_visible_height": log_visible_height,
            "button_text_width": button_text_width,
        }

    def wrap_text_characters(text: str, font: Any, max_width: int) -> list[str]:
        if not text:
            return [""]
        lines: list[str] = []
        current = ""
        for char in text:
            candidate = current + char
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = char if char != " " else ""
        if current:
            lines.append(current)
        if not lines:
            lines.append("")
        return lines

    def wrap_text_words(text: str, font: Any, max_width: int) -> list[str]:
        if not text:
            return [""]
        wrapped: list[str] = []
        for paragraph in text.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                wrapped.append("")
                continue
            line = words[0]
            for word in words[1:]:
                candidate = f"{line} {word}"
                if font.size(candidate)[0] <= max_width:
                    line = candidate
                else:
                    wrapped.append(line)
                    if font.size(word)[0] <= max_width:
                        line = word
                    else:
                        pieces = wrap_text_characters(word, font, max_width)
                        if pieces:
                            wrapped.extend(pieces[:-1])
                            line = pieces[-1]
                        else:
                            line = ""
            wrapped.append(line)
        return wrapped or [""]

    def build_button_entries(layout: dict[str, Any]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        text_width = layout["button_text_width"]
        button_min_height = button_font.get_linesize() + 16
        for func_name, func in functions:
            lines = wrap_text_characters(func_name, button_font, text_width)
            line_height = button_font.get_linesize()
            height = max(button_min_height, line_height * len(lines) + 12)
            entries.append({
                "name": func_name,
                "func": func,
                "lines": lines,
                "height": height,
            })
        return entries

    def clamp_scroll(offset: int, layout: dict[str, Any], entries: list[dict[str, Any]]) -> int:
        visible_height = layout["button_visible_height"]
        if visible_height <= 0:
            return 0
        if not entries:
            return 0
        total_height = sum(entry["height"] for entry in entries)
        total_height += button_spacing * (len(entries) - 1) if len(entries) > 1 else 0
        if total_height <= visible_height:
            return 0
        max_offset = total_height - visible_height
        return max(0, min(offset, max_offset))

    def append_log(message: str, *, is_error: bool = False) -> None:
        text = message if len(message) <= 800 else message[:797] + "..."
        log_lines.append((text, is_error))
        if len(log_lines) > 50:
            del log_lines[0]

    def invoke(func_name: str, func: Callable[[], Any]) -> None:
        try:
            result = func()
        except TypeError as exc:
            message = str(exc)
            append_log(f"{func_name} requires arguments: {message}", is_error=True)
            call_history.append({
                "name": func_name,
                "error": message,
            })
        except Exception as exc:  # pragma: no cover - runtime execution
            message = str(exc)
            append_log(f"{func_name} failed: {message}", is_error=True)
            call_history.append({
                "name": func_name,
                "error": message,
            })
        else:
            display = result
            if isinstance(display, bytes):
                try:
                    display = display.decode("utf-8")
                except Exception:
                    display = repr(display)
            if display is None:
                display_text = "None"
            else:
                display_text = str(display)
            if len(display_text) > 160:
                display_text = display_text[:157] + "..."
            append_log(f"{func_name} -> {display_text}")
            call_history.append({
                "name": func_name,
                "result": result,
                "result_preview": display_text,
            })

    try:
        running = True
        layout = compute_layout(screen.get_size())
        button_entries = build_button_entries(layout)
        scroll_step = button_font.get_linesize() + button_spacing
        wheel_step = max(1, scroll_step // 2)
        while running:
            # Update layout each frame to reflect current window size
            layout = compute_layout(screen.get_size())
            button_entries = build_button_entries(layout)
            scroll_step = button_font.get_linesize() + button_spacing
            wheel_step = max(1, scroll_step // 2)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_UP:
                        scroll_offset = clamp_scroll(scroll_offset - scroll_step, layout, button_entries)
                    elif event.key == pygame.K_DOWN:
                        scroll_offset = clamp_scroll(scroll_offset + scroll_step, layout, button_entries)
                elif event.type == pygame.VIDEORESIZE:
                    new_width = max(min_width, event.w)
                    new_height = max(min_height, event.h)
                    screen = pygame.display.set_mode((new_width, new_height), pygame.RESIZABLE)
                    layout = compute_layout((new_width, new_height))
                    button_entries = build_button_entries(layout)
                    scroll_offset = clamp_scroll(scroll_offset, layout, button_entries)
                elif event.type == pygame.MOUSEWHEEL:
                    scroll_offset = clamp_scroll(scroll_offset - event.y * wheel_step, layout, button_entries)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mouse_pos = event.pos
                    y_position = layout["button_list_top"] - scroll_offset
                    for entry in button_entries:
                        rect = pygame.Rect(
                            layout["button_panel"].x + 16,
                            y_position,
                            layout["button_panel"].width - 32,
                            entry["height"],
                        )
                        if rect.collidepoint(mouse_pos):
                            invoke(entry["name"], entry["func"])
                            break
                        y_position += entry["height"] + button_spacing

            scroll_offset = clamp_scroll(scroll_offset, layout, button_entries)

            screen.fill(background)
            button_panel = layout["button_panel"]
            log_panel = layout["log_panel"]
            pygame.draw.rect(screen, panel_bg, button_panel, border_radius=8)
            pygame.draw.rect(screen, panel_bg, log_panel, border_radius=8)

            title_surface = title_font.render(f"{project_name.title()} Dashboard", True, text_color)
            screen.blit(title_surface, (20, 16))

            instructions = button_font.render(instructions_text, True, text_color)
            instructions_pos = (button_panel.x + 16, button_panel.y + 10)
            screen.blit(instructions, instructions_pos)

            mouse_pos = pygame.mouse.get_pos()
            y_position = layout["button_list_top"] - scroll_offset
            clip_top = layout["button_list_top"]
            clip_bottom = layout["button_list_bottom"]
            for entry in button_entries:
                rect = pygame.Rect(
                    button_panel.x + 16,
                    y_position,
                    button_panel.width - 32,
                    entry["height"],
                )
                if rect.bottom < clip_top or rect.top > clip_bottom:
                    y_position += entry["height"] + button_spacing
                    continue
                is_hovered = rect.collidepoint(mouse_pos)
                color = button_hover if is_hovered else button_bg
                pygame.draw.rect(screen, color, rect, border_radius=6)
                line_height = button_font.get_linesize()
                total_text_height = line_height * len(entry["lines"])
                text_y = rect.y + (rect.height - total_text_height) // 2
                for line in entry["lines"]:
                    label_surface = button_font.render(line, True, text_color)
                    screen.blit(label_surface, (rect.x + 12, text_y))
                    text_y += line_height
                y_position += entry["height"] + button_spacing

            pygame.draw.rect(screen, panel_bg, log_panel, border_radius=8)
            log_title = button_font.render("Activity", True, text_color)
            screen.blit(log_title, (log_panel.x + 16, log_panel.y + 10))

            log_inner_width = max(20, log_panel.width - 32)
            log_y = layout["log_text_top"]
            available_height = layout["log_visible_height"]
            if available_height > 0:
                rendered_lines: list[tuple[str, tuple[int, int, int]]] = []
                consumed_height = 0
                for message, is_error in reversed(log_lines):
                    line_color = error_color if is_error else text_color
                    wrapped_lines = wrap_text_words(message, log_font, log_inner_width)
                    for line in reversed(wrapped_lines):
                        line_height = log_font.get_linesize()
                        if consumed_height + line_height > available_height and rendered_lines:
                            break
                        if consumed_height + line_height > available_height:
                            continue
                        rendered_lines.append((line, line_color))
                        consumed_height += line_height
                    if consumed_height >= available_height:
                        break
                rendered_lines.reverse()
                for text, color in rendered_lines:
                    log_surface = log_font.render(text, True, color)
                    screen.blit(log_surface, (log_panel.x + 16, log_y))
                    log_y += log_surface.get_height()
                    if log_y > log_panel.bottom - 20:
                        break

            pygame.display.flip()
            clock.tick(frame_rate)
    finally:
        pygame.quit()

    return {
        "project": project_name,
        "invocations": call_history,
    }
