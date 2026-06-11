import json
import os
import shutil
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk, filedialog

import vlc
from PIL import Image, ImageTk, ImageOps

from src.constants import TRACKS, DATA_PATH, LANDMARKER, TRACKS_NUMBERS, BACKGROUND
from src.tools import histo, plot_velocity_acc, movement_extraction, f0_extract, plot_pitch
from src.utils import millisecond_to_minute_second, split_id



class Application(tk.Frame):
    # region APPLICATION LOGIC
    # region INITIALIZATION
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        if not os.path.isdir("data/participants/"):
            os.mkdir("data/participants")
        self.master = master
        self.pack(fill="both", expand=True)

        self._init_state()
        self._init_video_backend()
        self._init_layout_values()

        self.build_toolbar(master)
        self.build_body()

        self.master.bind("<Configure>", self.on_window_resize)

        self.master.bind("<Left>", self.go_one_frame_back_bind_function)
        self.master.bind("<Right>", self.go_one_frame_forward_bind_function)
        self.master.bind("<space>", self.toggle_play_pause_bind_function)
        self.master.bind("<Key>", self.go_to_x_tenth_bind_function)

        if not self.settings["stop_displaying_help_at_beginning"]:
            # noinspection PyTypeChecker
            self.after(500, self.build_popup_info)

    def _init_state(self):
        self.PARTICIPANT_NAME: tk.StringVar = tk.StringVar(value="--Name--")
        self.PARTICIPANT_ID: tk.StringVar = tk.StringVar(value="--ID--")
        self.BODY_PART: tk.StringVar = tk.StringVar(value="--Body Part--")

        self.VIDEO_YEAR: int = datetime.now().year
        self.VIDEO_YEAR_ID: int = 1

        self.DATA_PATH_PARTICIPANT: str = DATA_PATH
        self.DATA_PATH_ID: str = DATA_PATH

        self.MILLISECONDS_BETWEEN_FRAMES: int = 60
        self.IMAGE_NAME: list[str] = ["", "", "f0.png"]

        with open("data/settings.json", "r", encoding="utf-8") as file:
            self.settings = json.load(file)

        self.VIDEO_LENGTH: int = -1
        self.IS_VIDEO_PLAYING: bool = False
        self.fps: int|None = None

        self.offset: int = 0
        self.curves_length: int = 0
        self.cursor_x: int = 0

        self.boolvar: tk.BooleanVar = tk.BooleanVar(value=self.settings["stop_displaying_help_at_beginning"])
        self.rodiobutton_choice: tk.StringVar = tk.StringVar(value="acceleration")

        self.old_peak_percentage: int
        self.old_peak_distance: int

        self.resize_after_id = None

    def _init_video_backend(self):
        self.vlc_player = None
        self.vlc_instance = None

    def _init_layout_values(self):
        self.master.update_idletasks()
        self.third_of_width: int = self.master.winfo_width() // 3
        self.label_width: int = 16

    # endregion INITIALIZATION

    # region SYSTEM
    def on_window_resize(self, event):
        width = self.master.winfo_width() // 3
        self.video_frame.config(
            width=width
        )
        self.graphs_frame.config(
            width=width
        )
        if self.resize_after_id is not None:
            self.after_cancel(self.resize_after_id)
            self.resize_after_id = None
        if self.IMAGE_NAME[0] != "" and self.IMAGE_NAME[1] != "":
            # noinspection PyTypeChecker
            self.resize_after_id = self.after(200, self.reload_images)

    def place_popup(self):
        x: int = self.master.winfo_rootx() + (self.master.winfo_width() // 2) - (self.popup.winfo_width() // 2)
        y: int = self.master.winfo_rooty() + (self.master.winfo_height() // 2) - (self.popup.winfo_height() // 2)
        self.popup.geometry(f"+{x}+{y}")

    def call_load_participant_popup(self):
        if os.listdir(DATA_PATH):
            self.build_load_participant_popup()
        else:
            #TODO toast
            self.popup = tk.Toplevel(self.master)
            self.popup.lift()
            self.popup.attributes("-topmost", True)
            self.popup.attributes("-topmost", False)

            tk.Label(
                self.popup,
                text="No participant found. Please create a participant first.",
                justify="left",
                padx=5,
                pady=5
            ).pack()

            self.after(2000, self.popup.destroy)

    def update_startup_info(self):
        self.settings["stop_displaying_help_at_beginning"] = self.boolvar.get()

        with open("data/settings.json", "w", encoding="utf-8") as file:
            json.dump(self.settings, file, indent=4)

    def free_vlc_player(self):
        if self.vlc_player is not None:
            self.vlc_player.stop()
            self.vlc_player.release()
            self.vlc_player = None
        if self.vlc_instance is not None:
            self.vlc_instance.release()
            self.vlc_instance = None

    def quit_application(self):
        self.free_vlc_player()
        self.master.destroy()

    def open_f0_entry(self):
        self.f0_frequency_entry.config(
            state="normal",
        )

    def close_f0_entry(self):
        self.f0_frequency_entry.config(
            state="readonly",
        )

    # region IMAGES
    def draw_image(self, image_path: str, frame: tk.Frame, canva: tk.Canvas, draw_line: bool = False):
        """
        Draw an image in the given canvas, resized to fit the given frame.
        :param image_path: Path to the image
        :param frame: Frame whose size is used for resizing
        :param canva: Canva where the image will be displayed
        :param draw_line: Ask if a line synced with the video player should be drawn
        """
        print("image_path :", image_path)

        frame.update_idletasks()
        canva.delete("all")
        if os.path.isfile(image_path):
            x: int = frame.winfo_width()
            y: int = frame.winfo_height()
            image_import = Image.open(image_path)
            image_resized = ImageOps.contain(
                image_import,
                (x, y)
            )
            image = ImageTk.PhotoImage(image_resized)
            canva.create_image(
                frame.winfo_width() // 2,
                frame.winfo_height() // 2,
                anchor="center",
                image=image,
            )
            canva.image = image

            if draw_line:
                self.set_cursor_coords(image=image_resized, canva=canva)

                progress: int = self.vlc_player.get_time() / self.VIDEO_LENGTH
                canva.create_line(
                    self.offset + progress * self.curves_length, self.y_top,
                    self.offset + progress * self.curves_length, self.y_bottom,
                    fill="red",
                    width=1,
                    tags=("cursor", "body parts cursor")
                )
                canva.bind("<Button-1>", self.on_click_canva_bind_function)
                canva.bind("<B1-Motion>", self.on_click_canva_bind_function)
        else:
            canva.create_text(
                frame.winfo_width() // 2,
                frame.winfo_height() // 2,
                anchor="nw",
                fill="red",
                text="ERROR : image not found !",
            )

    def put_image(self, image_path: str, frame: tk.Frame, container: tk.Label | tk.Button):
        """
        put the given image in the given container, resized to fit the given frame.
        :param image_path: Path to the image
        :param frame: Frame whose size is used for resizing
        :param container: Tkinter element where the image will be displayed
        """
        x: int = frame.winfo_width()
        y: int = frame.winfo_height()
        if os.path.isfile(image_path):
            frame.update_idletasks()
            image_import = Image.open(image_path)
            image_resized = ImageOps.contain(
                image_import,
                (x, y)
            )
            image = ImageTk.PhotoImage(image_resized)

            container.config(
                image=image,
            )
            container.image = image
        else:
            container.config(
                text="ERROR : image not found !",
                image="",
            )
            container.image = None

    def advance_progress_bar(self, parent: tk.Frame, progression_bar: ttk.Progressbar):
        progression_bar["value"] += 1
        parent.update_idletasks()

    def reload_images(self):
        self.draw_image(os.path.join(self.DATA_PATH_ID, self.IMAGE_NAME[0]), self.body_part_canva_frame,
                        self.body_part_canva, False) # TODO put back True after the # TEST
        self.draw_image(os.path.join(self.DATA_PATH_ID, self.IMAGE_NAME[1]), self.histogram_canvas_frame,
                        self.histogram_canvas)
        self.draw_image(os.path.join(self.DATA_PATH_ID, self.IMAGE_NAME[2]), self.f0_canva_frame,
                        self.f0_canva, True)  # TODO set True in the arguments when the right image will be used

    def search_curves_border(self, orientation: str, image: Image.Image, width: int, height: int):
        hypothetical_lines: list[int] = []
        threshold: int = 127

        if orientation == "horizontal":
            black_percentage: float = width * 0.7
            for y in range(height):
                black_pixels = 0

                for x in range(width):
                    actual_pixel = image.getpixel((x, y))

                    if actual_pixel < threshold:
                        black_pixels += 1

                if black_pixels > black_percentage:
                    hypothetical_lines.append(y)
        elif orientation == "vertical":
            black_percentage: float = height * 0.7
            for x in range(width):
                black_pixels = 0

                for y in range(height):
                    actual_pixel = image.getpixel((x, y))

                    if actual_pixel < threshold:
                        black_pixels += 1

                if black_pixels > black_percentage:
                    hypothetical_lines.append(x)

        return [hypothetical_lines[0], hypothetical_lines[-1]]

    def reset_images(self):
        self.body_part_canva.delete("all")
        self.f0_canva.delete("all")
        self.histogram_canvas.delete("all")
        self.acceleration_radiobutton.config(
            state="disabled",
        )
        self.velocity_radiobutton.config(
            state="disabled",
        )
        self.set_f0_entry(reset=True)
        self.set_parameters_to_default()

    # endregion IMAGES

    def wait_for_video_fps(self, attempt: int = 0):
        if attempt > 20:
            print("ERROR : too many attempts, cannot get video fps !")
            return
        if self.vlc_player.get_fps():
            self.fps = round(self.vlc_player.get_fps())
            histo(csv_path=os.path.join(self.DATA_PATH_ID, "movement_all.csv"),
                  f0_path=os.path.join(self.DATA_PATH_ID, "f0.csv"),
                  landmarks=TRACKS,
                  fps=self.fps,
                  output_path=self.DATA_PATH_ID
            )
            self.advance_progress_bar(parent=self.popup_footer, progression_bar=self.popup_progression_bar)

            plot_velocity_acc(os.path.join(self.DATA_PATH_ID, "movement_all.csv"), TRACKS, self.DATA_PATH_ID)
            print("- END")
            self.advance_progress_bar(parent=self.popup_footer, progression_bar=self.popup_progression_bar)
        else:
            self.after(200, self.wait_for_video_fps, attempt + 1)

    def reset(self):
        self.free_vlc_player()
        for child in self.video_frame.winfo_children():
            child.destroy()
        self.build_video_player(self.video_frame)
        self.build_video_controls(self.video_frame)
        self.reset_images()

        for widget in (
                self.body_part_drop_down_list,
                self.acceleration_radiobutton,
                self.velocity_radiobutton
        ):
            widget.config(
                state="disabled"
            )

    # endregion SYSTEM

    # region SETTERS
    def set_data_path_participant(self):
        self.DATA_PATH_PARTICIPANT = os.path.join(DATA_PATH, self.PARTICIPANT_NAME.get())

    def set_data_path_id(self):
        self.DATA_PATH_ID = os.path.join(self.DATA_PATH_PARTICIPANT, self.PARTICIPANT_ID.get())

    def set_infos_labels(self, name: str = " - ", video_year: str = " - "):
        """
        Set the Labels text in the information section.
        :param name: Name of the participant
        :param video_year: Year of the video
        """
        self.participant_name_label.config(
            text=name
        )
        self.video_year_label.config(
            text=video_year
        )

    def set_parameters_to_default(self):
        self.peak_percentage_entry.delete(0, tk.END)
        self.peak_percentage_entry.insert(0, "75")
        self.old_peak_percentage = 75
        self.peak_distance_entry.delete(0, tk.END)
        self.peak_distance_entry.insert(0, "5")
        self.old_peak_distance = 5

    def set_time_scale_length(self, attempt=0):
        if attempt > 20:
            print("ERROR : too many attempts, cannot get time scale length !")
            return
        self.VIDEO_LENGTH = self.vlc_player.get_length()
        if attempt <= 20 and self.VIDEO_LENGTH > 0:

            self.video_time_scale.config(
                to=self.VIDEO_LENGTH
            )
            self.video_time_scale.set(0)

            return
        else:
            self.after(100, self.set_time_scale_length, attempt + 1)

    def set_f0_entry(self, reset: bool = False, attempt: int = 0):
        self.open_f0_entry()

        if attempt >= 20:
            print("ERROR : too many attempts, cannot get f0 entry !")
            self.close_f0_entry()
            return
        if attempt < 20:
            if reset:
                self.f0_frequency_entry.delete(0, tk.END)
                self.f0_frequency_entry.insert(0, " - ")
                self.close_f0_entry()
                return

            self.fps: int = round(self.vlc_player.get_fps())

            if self.fps <= 0:
                self.after(100, self.set_f0_entry, reset, attempt + 1)
                self.close_f0_entry()
                return

            if len(str(self.fps)) > 3:
                self.f0_frequency_entry.config(
                    width=len(str(self.fps))
                )
            if self.fps > 0:
                self.f0_frequency_entry.delete(0, tk.END)
                self.f0_frequency_entry.insert(0, str(self.fps))
                self.MILLISECONDS_BETWEEN_FRAMES = int(1000 / self.fps) + 1

            self.close_f0_entry()

    def set_video_time_label(self, milliseconds: int):
        self.video_time_label.config(
            text=millisecond_to_minute_second(milliseconds)
        )

    def set_image_name(self):
        self.IMAGE_NAME[0] = f"{self.rodiobutton_choice.get()}_{self.BODY_PART.get()}.png"
        self.IMAGE_NAME[1] = f"histogram_{self.rodiobutton_choice.get()}_{self.BODY_PART.get()}.png"

    def set_cursor_coords(self, image, canva):
        image = image.convert("RGB")
        width: int
        height: int
        width, height = image.size
        x_margin = (canva.winfo_width() - image.width) // 2
        y_margin = (canva.winfo_height() - image.height) // 2

        grayed_image = image.convert("L")
        horizontal_borders: list[int] = self.search_curves_border("horizontal", grayed_image, width, height)
        vertical_borders: list[int] = self.search_curves_border("vertical", grayed_image, width, height)

        self.y_top: int = y_margin + horizontal_borders[0] + 4
        self.y_bottom: int = y_margin + horizontal_borders[-1] + 3

        offset_found = False
        curve_beginning: int = 0
        curve_ending: int = 0
        for x in range(vertical_borders[0] + 2, vertical_borders[1]):
            for y in range(horizontal_borders[0], horizontal_borders[1]):
                r, g, b = image.getpixel((x, y))

                if b > 100 and b > r * 1.2 and b > g * 1.2:
                    curve_beginning = x + 3
                    offset_found = True
                    break

            if offset_found:
                break
        offset_found = False
        for x in range(vertical_borders[1], vertical_borders[0] + 2, -1):
            for y in range(horizontal_borders[0], horizontal_borders[1]):
                r, g, b = image.getpixel((x, y))

                if b > 100 and b > r * 1.2 and b > g * 1.2:
                    curve_ending = x + 3
                    offset_found = True
                    break

            if offset_found:
                break

        self.offset = x_margin + curve_beginning
        self.curves_length: int = curve_ending - curve_beginning
        self.cursor_x = self.offset + (self.vlc_player.get_time() / self.VIDEO_LENGTH) * self.curves_length

    # endregion SETTERS

    # region CALLBACKS
    # region VIDEO CONTROLS
    def play(self):
        if not self.vlc_player.is_playing():
            if self.vlc_player.get_state() == vlc.State.Ended:
                self.vlc_player.stop()
                self.vlc_player.set_time(0)
                self.video_time_scale.set(0)
            self.play_pause_button.config(
                text="||"
            )
            self.vlc_player.play()
            self.IS_VIDEO_PLAYING = True
            # noinspection PyTypeChecker
            self.after(250, self.update_video_time_scale)

    def pause(self):
        if self.vlc_player.is_playing():
            self.play_pause_button.config(
                text=">"
            )
            self.IS_VIDEO_PLAYING = False
            self.vlc_player.pause()

    def pause_at_start(self, attempt: int = 0):
        if attempt >= 30:
            print("ERROR : cannot pause")
            return
        if self.vlc_player.is_playing():
            self.pause()
            self.vlc_player.set_time(0)
            return
        else:
            self.after(250, self.pause_at_start, attempt + 1)
            return

    def toggle_play_pause(self):
        if self.vlc_player.is_playing():
            self.pause()
        else:
            self.play()

    def video_time_scale_function(self, value: str):
        state = self.vlc_player.get_state()
        if state not in (
                vlc.State.NothingSpecial,
                vlc.State.Opening,
                vlc.State.Buffering,
        ):
            value: int = int(value)
            self.set_video_time_label(value)
            self.update_body_part_cursor(value)

            if not self.IS_VIDEO_PLAYING:
                self.vlc_player.set_time(value)

    def update_video_time_scale(self, iteration: int = 0):
        if self.vlc_player.is_playing():
            time: int = self.vlc_player.get_time()
            self.video_time_scale.set(time)
            self.after(100, self.update_video_time_scale, iteration + 1)
            return

    def update_body_part_cursor(self, time_ms: int):
        video_length = self.vlc_player.get_length()
        if video_length != 0:
            progress: int = time_ms / video_length
        else:
            progress = 0
        new_x = self.offset + progress * self.curves_length

        dx = new_x - self.cursor_x
        self.body_part_canva.move("cursor", dx, 0)
        self.f0_canva.move("cursor", dx, 0)

        self.cursor_x = new_x

    def go_one_frame_back(self):
        self.pause()
        self.video_time_scale.set(self.vlc_player.get_time() - self.MILLISECONDS_BETWEEN_FRAMES)

    def go_one_frame_forward(self):
        self.pause()
        self.video_time_scale.set(self.vlc_player.get_time() + self.MILLISECONDS_BETWEEN_FRAMES)

    # endregion VIDEO CONTROLS

    # region COMMAND CALLBACKS
    def load_participant_confirm(self):
        self.set_parameters_to_default()
        self.set_infos_labels(self.PARTICIPANT_NAME.get(), str(self.VIDEO_YEAR))

        self.load_video()

        self.body_part_drop_down_list.config(
            state="normal",
        )

        self.popup.destroy()
        self.master.focus_set()

    def load_participant_cancel(self, old_values: list):
        self.PARTICIPANT_NAME.set(old_values[0])
        self.DATA_PATH_PARTICIPANT = old_values[1]
        self.VIDEO_YEAR = old_values[2]
        self.VIDEO_YEAR_ID = old_values[3]
        self.DATA_PATH_ID = old_values[4]

        self.popup.destroy()

    def radiobutton_function(self):
        self.set_image_name()
        self.reload_images()

    def option_confirm_button_command(self):
        peak_percentage: int = int(self.peak_percentage_entry.get())
        peak_distance: int = int(self.peak_distance_entry.get())

        if self.old_peak_percentage != peak_percentage or self.old_peak_distance != peak_distance:
            self.old_peak_percentage = peak_percentage
            self.old_peak_distance = peak_distance

            histo(csv_path=os.path.join(self.DATA_PATH_ID, "movement_all.csv"),
                  f0_path=os.path.join(self.DATA_PATH_ID, "f0.csv"),
                  landmarks=TRACKS,
                  fps=self.fps,
                  threshold_percentile=peak_percentage,
                  peak_distance=peak_distance,
                  output_path=self.DATA_PATH_ID,
            )
            self.reload_images()

    # endregion COMMAND CALLBACKS

    # region BIND FUNCTIONS CALLBACKS
    def participants_drop_down_list_bind_function(self, participant_name, next_ddl: tk.OptionMenu):
        self.load_participant_name_context()

        values = sorted(
            [
                name for name in os.listdir(self.DATA_PATH_PARTICIPANT)
                if os.path.isdir(os.path.join(self.DATA_PATH_PARTICIPANT, name))
            ],
            key=split_id
        )

        next_ddl.destroy()

        next_ddl = tk.OptionMenu(
            self.ddls_frame,
            self.PARTICIPANT_ID,
            *values,
            command=self.id_drop_down_list_bind_function
        )
        next_ddl.config(
            width=20,
        )
        next_ddl.pack(
            side="top",
            padx=5,
            pady=5,
        )

    def id_drop_down_list_bind_function(self, participant_id):
        self.VIDEO_YEAR, self.VIDEO_YEAR_ID = split_id(participant_id)

        self.load_participant_id_context()

        self.load_participant_button.config(state="normal")

    def body_part_drop_down_list_bind_function(self, body_part):
        if self.acceleration_radiobutton["state"] == "disabled" or self.velocity_radiobutton["state"] == "disabled":
            for widget in (
                    self.acceleration_radiobutton,
                    self.velocity_radiobutton
            ):
                widget.config(
                    state="normal"
                )

        self.set_image_name()
        self.reload_images()

        self.master.focus_set()

    def toggle_play_pause_bind_function(self, event: tk.Event):
        self.toggle_play_pause()

    def go_one_frame_back_bind_function(self, event: tk.Event):
        self.go_one_frame_back()

    def go_one_frame_forward_bind_function(self, event: tk.Event):
        self.go_one_frame_forward()

    def go_to_x_tenth_bind_function(self, event: tk.Event):
        if event.char.isdigit():
            n: int = int(event.char)
            targeted_time: int = self.VIDEO_LENGTH * n // 10
            self.vlc_player.set_time(targeted_time)
            self.video_time_scale.set(targeted_time)

    def on_click_canva_bind_function(self, event: tk.Event):
        pos_x = event.x - self.offset
        if 0 <= pos_x <= self.curves_length:
            targeted_time = int(self.VIDEO_LENGTH * (pos_x / self.curves_length))
            self.video_time_scale.set(targeted_time)
        if pos_x < 0:
            self.video_time_scale.set(0)
        if pos_x > self.curves_length:
            self.video_time_scale.set(self.VIDEO_LENGTH)

    # endregion BIND FUNCTIONS CALLBACKS
    # endregion CALLBACKS

    # region PARTICIPANT WORKFLOW
    def validate_participant_form(self):
        # TODO check the execution thread (name & video year not set on creation, maybe there's more)
        """
        Gets the values from the form to create the new participant's structure and set values with them
        """
        if self.name_entry.get() and (
                self.video_path_entry.get() and os.path.exists(self.video_path_entry.get())) and (
                self.video_year_entry.get() and len(self.video_year_entry.get()) == 4):
            self.master.config(cursor="watch")
            self.popup.config(cursor="watch")
            self.master.update_idletasks()
            self.popup_status_label.config(
                relief="groove",
                bg="#fdf1b8",
                text="LOADING..."
            )
            self.popup_status_label.pack(
                side="left",
                fill="y",
                anchor="center",
            )
            self.popup_progression_bar.pack(
                side="left",
                fill="x",
                padx=5,
                expand=True,
            )
            self.popup.update_idletasks()

            self.create_participant_tree(self.name_entry.get(),
                                         self.video_path_entry.get(), int(self.video_year_entry.get()))
            self.master.config(cursor="")
            self.popup.config(cursor="")
            self.popup.destroy()
        else:
            if not os.path.exists(self.video_path_entry.get()):
                self.popup_status_label.config(
                    text="ERROR : Video not found"
                )
            elif not len(self.video_year_entry.get()) == 4:
                self.popup_status_label.config(
                    text="ERROR : Wrong year format"
                )
            else:
                self.popup_status_label.config(
                    text="ERROR : All field are not filled"
                )

            self.popup_status_label.pack(
                side="top",
                fill="y",
                expand=True,
                anchor="center",
            )

    def create_participant_tree(self, name: str = "name", video_path: str = "data/meteo4.mp4", video_year: int = 2026): #TODO remake that function according to the new popup
        """
        Initialise the data for a new participant:
        - Create the participant's folders
        - Write the data to a CSV file
        - Copy the video given to the participant's folder as "video.mp4"
        """

        print("  -CREATE PARTICIPANT TREE-")
        print("values:")
        print("name :", name)
        print("video_path :", video_path)
        print("video_year :", video_year)

        self.PARTICIPANT_NAME.set(name)

        self.set_data_path_participant()

        if not os.path.exists(self.DATA_PATH_PARTICIPANT):
            os.mkdir(self.DATA_PATH_PARTICIPANT)
        self.load_participant_name_context()
        print("- Set of the name")
        self.advance_progress_bar(parent=self.popup_footer, progression_bar=self.popup_progression_bar)

        self.VIDEO_YEAR = video_year
        self.VIDEO_YEAR_ID = self.get_next_video_year_id(self.VIDEO_YEAR)

        self.PARTICIPANT_ID.set(str(self.VIDEO_YEAR) + "-" + str(self.VIDEO_YEAR_ID))

        self.load_participant_id_context()
        os.mkdir(self.DATA_PATH_ID)
        print("- Set of the year ID")
        self.advance_progress_bar(parent=self.popup_footer, progression_bar=self.popup_progression_bar)

        self.set_infos_labels(name=name, video_year=str(video_year))

        shutil.copy(video_path, os.path.join(self.DATA_PATH_ID, "video.mp4"))
        self.load_video()

        print("- Making a copy of the video into the new folder")
        self.advance_progress_bar(parent=self.popup_footer, progression_bar=self.popup_progression_bar)
        self.set_infos_labels(name=name, video_year=str(video_year))

        movement_extraction(video_path, TRACKS, LANDMARKER, TRACKS_NUMBERS, self.DATA_PATH_ID, False)
        print("- Getting the csvs from the video")
        self.advance_progress_bar(parent=self.popup_footer, progression_bar=self.popup_progression_bar)
        self.set_infos_labels(name=name, video_year=str(video_year))

        self.set_infos_labels(name=name, video_year=str(video_year))

        f0_extract("data/meteoaudio.mp3", os.path.join(self.DATA_PATH_ID, "f0.csv"))
        plot_pitch("data/meteoaudio.mp3", self.DATA_PATH_ID)

        print("- Making histograms")
        self.set_parameters_to_default()

        self.set_infos_labels(name=name, video_year=str(video_year))

        self.wait_for_video_fps()

    def get_next_video_year_id(self, video_year: int):
        """
        Return the next available id for a given video year.
        :param video_year: The year to check
        :return: The next available id for that year
        """
        cpt = 0
        for file in os.listdir(self.DATA_PATH_PARTICIPANT):
            if str(video_year) in file:
                cpt = cpt + 1
        return cpt + 1

    def load_participant_name_context(self):
        self.reset()


        self.set_data_path_participant()
        self.set_infos_labels(name=self.PARTICIPANT_NAME.get())


        self.video_year_label.config(
            text=" - "
        )

    def load_participant_id_context(self):
        self.reset_images()
        self.set_data_path_id()
        self.set_infos_labels(name=self.PARTICIPANT_NAME.get(), video_year=str(self.VIDEO_YEAR))

        self.body_part_drop_down_list.config(
            state="normal"
        )
        self.BODY_PART.set(" --body parts--")

    def load_video(self):
        """
        Load and display the video:
         - Load the video from the DATA_PATH_ID directory
         - Display it in the video Frame
         - Configure the time slider
         - Update the f0 frequency Label with the video FPS
        """
        if self.vlc_player:
            media = self.vlc_instance.media_new(os.path.join(self.DATA_PATH_ID, "video.mp4"))
            self.vlc_player.set_media(media)

            self.master.update()
            self.vlc_player.set_xwindow(self.video_player_frame.winfo_id())

            self.play()
            self.pause_at_start()

            self.set_time_scale_length()
            # noinspection PyTypeChecker
            self.after(100, self.set_f0_entry)
        else:
            tk.Label(
                self.video_player_frame,
                text="PROBLEM",
                fg="red"
            ).pack()

    def browse_for_mp4(self):
        path: str = filedialog.askopenfilename(
            parent=self.popup,
            filetypes=[("Video", "*.mp4")]
        )
        if path and os.path.exists(path):
            if self.video_path_entry.get():
                self.video_path_entry.delete(0, tk.END)
                self.video_path_entry.insert(0, path)
            else:
                self.video_path_entry.insert(0, path)
    # endregion PARTICIPANT WORKFLOW
    # endregion OTHER METHODS



    # region INTERFACE BUILDING
    # region BUILDING POPUPS
    # region BUILDING NEW PARTICIPANT POPUP
    def build_popup_new_participant(self):
        self.popup = tk.Toplevel(self.master)
        self.popup.title("New Participant")
        self.popup.lift()
        self.popup.attributes("-topmost", True)
        self.popup.attributes("-topmost", False)

        labels_width = 10

        self.build_popup_new_participant_name_entry(self.popup, labels_width)
        self.build_popup_new_participant_video_selector(self.popup, labels_width)
        self.build_popup_new_participant_video_year_entry(self.popup, labels_width)

        self.build_popup_new_participant_footer(self.popup)

        self.popup.update_idletasks()
        self.place_popup()

    def build_popup_new_participant_name_entry(self, parent: tk.Frame | tk.Toplevel, width: int):
        frame = tk.Frame(
            parent
        )
        frame.pack(side="top", fill="x")
        tk.Label(
            frame,
            text="Name :",
            anchor="e",
            width=width
        ).pack(
            side="left",
            padx=5,
            pady=5
        )
        self.name_entry = tk.Entry(
            frame,
            bg="white",
            width=20
        )
        self.name_entry.pack(
            side="left",
            padx=5,
            pady=5
        )

    def build_popup_new_participant_video_selector(self, parent: tk.Frame | tk.Toplevel, width: int):
        frame = tk.Frame(
            parent
        )
        frame.pack(
            side="top",
            fill="x"
        )
        tk.Label(
            frame,
            text="Video :",
            anchor="e",
            width=width
        ).pack(
            side="left",
            padx=5,
            pady=5
        )
        self.video_path_entry = tk.Entry(
            frame,
            bg="white",
            width=50
        )
        self.video_path_entry.pack(
            side="left",
            padx=5,
            pady=5
        )
        video_selector = tk.Button(
            frame,
            bg=BACKGROUND,
            text="Browse...",
            command=self.browse_for_mp4
        )
        video_selector.pack(
            side="left",
            padx=5,
            pady=5
        )

    def build_popup_new_participant_video_year_entry(self, parent: tk.Frame | tk.Toplevel, width: int):
        frame = tk.Frame(
            parent
        )
        frame.pack(
            side="top",
            fill="x"
        )
        tk.Label(
            frame,
            text="Video year :",
            anchor="e",
            width=width
        ).pack(
            side="left",
            padx=5,
            pady=5
        )

        self.video_year_entry = tk.Entry(
            frame,
            background="white",
            width=4,
            validate="key",
            validatecommand=(
                self.register(
                    lambda value: (value.isdigit() or value == "") and len(value) <= 4
                ),
                "%P"
            )
        )
        self.video_year_entry.pack(
            side="left",
            padx=5,
            pady=5
        )

    def build_popup_new_participant_footer(self, parent: tk.Frame | tk.Toplevel):
        self.popup_footer = tk.Frame(
            parent,
        )
        self.popup_footer.pack(
            side="bottom",
            fill="x",
        )

        self.popup_status_label = tk.Label(
            self.popup_footer,
            borderwidth=2,
            relief="raised",
            bg="red",
            padx=5,
        )

        self.popup_progression_bar = ttk.Progressbar(
            self.popup_footer,
            orient="horizontal",
            mode="determinate",
            maximum=6,
        )

        tk.Button(
            self.popup_footer,
            fg="red",
            text="Cancel",
            command=self.popup.destroy
        ).pack(
            side="right"
        )
        tk.Button(
            self.popup_footer,
            fg="green",
            text="Confirm",
            command=self.validate_participant_form
        ).pack(
            side="right",
        )

    # endregion BUILDING NEW PARTICIPANT POPUP

    # region BUILDING INFO POPUP
    def build_popup_info(self):
        self.popup = tk.Toplevel(self.master)
        self.popup.title("Infos")
        self.popup.lift()
        self.popup.attributes("-topmost", True)
        self.popup.attributes("-topmost", False)

        tk.Label(
            self.popup,
            text="Welcome to the Gesture and Synchrony Analyser\n\nThis free software enables the computation and analysis of gesture and speech synchrony in video data. It is based on the research of Chavez Miranda et al. (2026) and adapted from Pouw and Dixon (2019).\nTo learn more or contribute to the project, visit our GitHub repository:",
            wraplength=700,
            justify="left",
            padx=5,
            pady=5
        ).pack(
            side="top"
        )

        link_label = tk.Label(
            self.popup,
            text="https://github.com/laurachaves/gesture_speech",
            fg="blue",
            cursor="hand2",
            anchor="w",
        )
        link_label.pack(
            side="top",
            fill="x",
        )
        link_label.bind(
            "<Button-1>",
            lambda event:
            webbrowser.open("https://github.com/laurachaves/gesture_speech")
        )
        link_label.bind(
            "<Enter>",
            lambda event:
            link_label.config(
                fg="darkblue",
            )
        )
        link_label.bind(
            "<Leave>",
            lambda event:
            link_label.config(
                fg="blue",
            )
        )

        footer = tk.Frame(
            self.popup,
        )
        footer.pack(
            fill="x",
            side="bottom"
        )

        self.stop_showing_info_popup_checkbutton = tk.Checkbutton(
            footer,
            text="stop showing this help at the beginning",
            variable=self.boolvar,
            command=self.update_startup_info
        )
        self.stop_showing_info_popup_checkbutton.pack(
            side="left"
        )

        tk.Button(
            footer,
            fg="red",
            bg=BACKGROUND,
            text="Back",
            command=self.popup.destroy
        ).pack(
            side="right",
            padx=5,
            pady=5
        )

        self.popup.update_idletasks()
        self.place_popup()

    # endregion BUILDING INFO POPUP

    # region BUILDING LOAD PARTICIPANT POPUPS
    def build_load_participant_popup(self):
        self.popup = tk.Toplevel(self.master)
        self.popup.title("Load Participant")
        self.popup.lift()
        self.popup.attributes("-topmost", True)
        self.popup.attributes("-topmost", False)

        old_participant_name = self.PARTICIPANT_NAME.get()
        old_data_path_participant = self.DATA_PATH_PARTICIPANT
        old_video_year = self.VIDEO_YEAR
        old_video_year_id = self.VIDEO_YEAR_ID
        old_data_path_id = self.DATA_PATH_ID

        olds = [
            old_participant_name,
            old_data_path_participant,
            old_video_year,
            old_video_year_id,
            old_data_path_id
        ]

        self.ddls_frame = tk.Frame(
            self.popup
        )
        self.ddls_frame.pack()
        # region PARTICIPANT
        participants = sorted(os.listdir("data/participants/"))
        participants_drop_down_list = tk.OptionMenu(
            self.ddls_frame,
            self.PARTICIPANT_NAME,
            *participants,
            command=lambda participant_name: self.participants_drop_down_list_bind_function(participant_name=participant_name, next_ddl=id_drop_down_list),
        )
        participants_drop_down_list.config(
            width=20
        )
        participants_drop_down_list.pack(
            side="top",
            padx=5,
            pady=5,
        )
        # endregion PARTICIPANT

        # region ID DDL
        id_drop_down_list = tk.OptionMenu(
            self.ddls_frame,
            self.PARTICIPANT_ID,
            "You shouldn't be able to see that"
        )
        id_drop_down_list.config(
            width=20,
            state="disabled"
        )
        id_drop_down_list.pack(
            side="top",
            padx=5,
            pady=5,
        )
        # endregion ID DDL

        # region FOOTER
        footer = tk.Frame(
            self.popup,
        )
        footer.pack()
        self.load_participant_button = tk.Button(
            footer,
            command=self.load_participant_confirm,
            fg="green",
            text="Confirm",
            state="disabled"
        )
        cancel_button = tk.Button(
            footer,
            command=lambda: self.load_participant_cancel(olds),
            fg="red",
            text="Cancel",
        )

        cancel_button.pack(
            side="right"
        )
        self.load_participant_button.pack(
            side="right"
        )
        # endregion FOOTER

        self.place_popup()

    # endregion BUILDING LOAD PARTICIPANT POPUPS

    # endregion BUILDING POPUPS

    # region BUILDING BODY
    def build_body(self):
        # =========================
        # ===== BODY FRAME =====
        body = tk.Frame(
            self
        )
        body.pack(fill="both", expand=True)
        # =========================
        self.build_video_panel(body)

        # HACK instead of having to deal with putting the combobox in grid, I have made 2 more Frames to mimic a grid system
        # ==========================
        # ===== BODY PARTS DDL =====
        self.body_part_drop_down_list = tk.OptionMenu(
            body,
            self.BODY_PART,
            *TRACKS,
            command=self.body_part_drop_down_list_bind_function
        )
        self.body_part_drop_down_list.config(
            state="disabled",
        )
        self.body_part_drop_down_list.pack(
            side="top",
            fill="x"
        )
        # =============================================
        self.build_signal_curves_panel(body)
        self.build_histogram_and_details_panel(body)
        self.set_infos_labels()

    # region BUILDING TOOLBAR
    def build_toolbar(self, window: tk.Tk):
        toolbar = tk.Menu(
            window,
        )

        # region MENU FILE
        menu_file = tk.Menu(
            toolbar,
            tearoff=0,
        )
        menu_file.add_command(
            label="New Participant",
            command=self.build_popup_new_participant
        )
        menu_file.add_command(
            label="Load Participant",
            command=self.call_load_participant_popup
        )
        menu_file.add_separator()
        menu_file.add_command(
            label="QUIT",
            foreground="red",
            command=self.quit_application
        )

        toolbar.add_cascade(
            label="File",
            menu=menu_file
        )
        # endregion MENU FILE

        toolbar.add_command(
            label="Help",
            command=self.build_popup_info,
        )

        window.config(menu=toolbar)

    # endregion BUILDING TOOLBAR

    # region BUILDING VIDEO
    def build_video_panel(self, parent: tk.Frame):
        self.video_frame = tk.Frame(
            parent,
            # bg="#AF0000",
            width=self.third_of_width,
            padx=10,
            pady=10,
            borderwidth=3,
            relief="sunken"
        )
        self.video_frame.pack(
            side="left",
            fill="y",
        )
        self.video_frame.pack_propagate(False)
        self.build_video_player(self.video_frame)
        self.build_video_controls(self.video_frame)

    def build_video_player(self, parent: tk.Frame):
        self.vlc_instance = vlc.Instance()
        self.vlc_player = self.vlc_instance.media_player_new()

        self.video_player_frame = tk.Frame(
            parent
        )
        self.video_player_frame.pack(
            side="top",
            fill="both",
            expand=True
        )
        self.video_player_frame.pack_propagate(False)

    def build_video_controls(self, parent: tk.Frame):
        frame = tk.Frame(
            parent,
        )
        frame.pack(
            side="top",
            fill="x"
        )

        one_frame_back_button = tk.Button(
            frame,
            bg=BACKGROUND,
            width=1,
            text="-1",
            command=self.go_one_frame_back
        )
        one_frame_back_button.pack(
            side="left"
        )

        self.play_pause_button = tk.Button(
            frame,
            bg=BACKGROUND,
            width=1,
            text=">",
            anchor="center",
            command=self.toggle_play_pause
        )
        self.play_pause_button.pack(
            side="left"
        )

        one_frame_forward_button = tk.Button(
            frame,
            bg=BACKGROUND,
            width=1,
            text="+1",
            command=self.go_one_frame_forward
        )
        one_frame_forward_button.pack(
            side="left"
        )

        self.video_time_label = tk.Label(
            frame,
            bg="white",
            text="00:00",
            borderwidth=2,
            relief="sunken",
            width=5,
            anchor="e",
        )
        self.video_time_label.pack(
            side="right",
        )

        self.video_time_scale = tk.Scale(
            frame,
            from_=0,
            to=0,
            orient="horizontal",
            showvalue=False,
            command=self.video_time_scale_function
        )
        self.video_time_scale.pack(
            fill="x",
            expand=True
        )

    # endregion BUILDING VIDEO

    # region BUILDING SIGNAL CURVES
    def build_signal_curves_panel(self, parent: tk.Frame):
        self.graphs_frame = tk.Frame(
            parent,
            # bg="#00AF00",
            width=self.third_of_width,
        )
        self.graphs_frame.pack(side="left", fill="y")
        self.graphs_frame.pack_propagate(False)

        self.build_body_part_curve(self.graphs_frame)
        self.build_f0_curve(self.graphs_frame)

    def build_body_part_curve(self, parent: tk.Frame):
        self.body_part_canva_frame = tk.Frame(
            parent,
            borderwidth=3,
            relief="sunken"
        )
        self.body_part_canva_frame.pack(
            side="top",
            fill="both",
            expand=True,
            padx=5,
            pady=5
        )
        self.body_part_canva_frame.pack_propagate(False)

        self.body_part_canva = tk.Canvas(
            self.body_part_canva_frame,
        )
        self.body_part_canva.pack(
            fill="both",
            expand=True,
        )

    def build_f0_curve(self, parent: tk.Frame):
        self.f0_canva_frame = tk.Frame(
            parent,
            borderwidth=3,
            relief="sunken"
        )
        self.f0_canva_frame.pack(
            side="top",
            fill="both",
            expand=True,
            padx=5,
            pady=5
        )
        self.f0_canva_frame.pack_propagate(False)

        self.f0_canva = tk.Canvas(
            self.f0_canva_frame,
            # bg="#00FFAF"
        )
        self.f0_canva.pack(
            fill="both",
            expand=True,
        )

    # endregion SIGNAL CURVES

    # region BUILDING HISTOGRAM AND DETAILS
    def build_histogram_and_details_panel(self, parent: tk.Frame):
        frame = tk.Frame(
            parent,
            # bg="#0000AF",
            # width=self.third_of_width,
        )
        frame.pack(
            side="left",
            fill="both",
            expand=True
        )
        frame.pack_propagate(False)

        self.build_histogram(frame)
        self.build_details_panel(frame)

    def build_histogram(self, parent: tk.Frame):
        self.histogram_canvas_frame = tk.Frame(
            parent,
            borderwidth=3,
            relief="sunken"
        )
        self.histogram_canvas_frame.pack(
            side="top",
            fill="both",
            expand=True,
            padx=5,
            pady=5
        )
        self.histogram_canvas_frame.pack_propagate(False)

        self.histogram_canvas = tk.Canvas(
            self.histogram_canvas_frame
        )
        self.histogram_canvas.pack(
            fill="both",
            expand=True,
        )

    # region BUILDING DETAILS
    def build_details_panel(self, parent: tk.Frame):
        frame = tk.Frame(
            parent,
            borderwidth=3,
            relief="groove"
        )
        frame.pack(
            side="top",
            fill="both",
            expand=True,
            padx=5,
            pady=5
        )
        frame.pack_propagate(False)

        self.build_participant_name_info(frame)
        self.build_video_year_info(frame)
        self.build_f0_frequency_info(frame)

        # ======================
        # ===== SEPARATION =====
        ttk.Separator(
            frame,
            orient="horizontal"
        ).pack(fill="x")
        # ======================

        self.build_peak_percentage_setting(frame)
        self.build_peak_distance_setting(frame)

        self.option_confirm_button = tk.Button(
            frame,
            width=12,
            text="Confirm",
            command=self.option_confirm_button_command
        )
        self.option_confirm_button.pack()

        # ======================
        # ===== SEPARATION =====
        ttk.Separator(
            frame,
            orient="horizontal"
        ).pack(fill="x")
        # ======================

        self.acceleration_radiobutton = tk.Radiobutton(
            frame,
            text="Acceleration",
            variable=self.rodiobutton_choice,
            value="acceleration",
            command=self.radiobutton_function,
            justify="left",
            anchor="w",
            state="disabled"
        )
        self.acceleration_radiobutton.pack(
            fill="x"
        )

        self.velocity_radiobutton = tk.Radiobutton(
            frame,
            text="Velocity",
            variable=self.rodiobutton_choice,
            value="velocity",
            command=self.radiobutton_function,
            justify="left",
            anchor="w",
            state="disabled"
        )
        self.velocity_radiobutton.pack(
            fill="x"
        )

    # region BUILDING INFOS
    def build_participant_name_info(self, parent: tk.Frame):
        frame = tk.Frame(
            parent
        )
        frame.pack(
            side="top",
            fill="x"
        )

        tk.Label(
            frame,
            text="Participant name : ",
            width=self.label_width,
            anchor="e"
        ).pack(
            side="left"
        )

        self.participant_name_label = tk.Label(
            frame
        )
        self.participant_name_label.pack(
            side="left"
        )
        if self.PARTICIPANT_NAME.get() != "--Name--":
            self.participant_name_label.config(
                text=self.PARTICIPANT_NAME.get()
            )
        else:
            self.participant_name_label.config(
                text=" - "
            )

    def build_video_year_info(self, parent: tk.Frame):
        frame = tk.Frame(
            parent
        )
        frame.pack(
            side="top",
            fill="x"
        )

        tk.Label(
            frame,
            text="Video year : ",
            width=self.label_width,
            anchor="e"
        ).pack(
            side="left"
        )

        self.video_year_label = tk.Label(
            frame,
            text=str(self.VIDEO_YEAR)
        )
        self.video_year_label.pack(
            side="left"
        )

    def build_f0_frequency_info(self, parent: tk.Frame):
        frame = tk.Frame(
            parent
        )
        frame.pack(
            side="top",
            fill="x"
        )

        tk.Label(
            frame,
            text="f0's frequency : ",
            width=self.label_width,
            anchor="e"
        ).pack(
            side="left"
        )

        self.f0_frequency_entry = tk.Entry(
            frame,
            bg="white",
            width=3,
            validate="all",
        )
        self.f0_frequency_entry.insert(0, " - ")
        self.f0_frequency_entry.config(
            state="readonly"
        )
        self.f0_frequency_entry.pack(
            side="left"
        )

        tk.Label(
            frame,
            text="Hz"
        ).pack(
            side="left"
        )

    # endregion BUILDING INFOS

    # region BUILDING SETTINGS
    def build_peak_percentage_setting(self, parent: tk.Frame):
        frame = tk.Frame(
            parent
        )
        frame.pack(
            side="top",
            fill="x"
        )

        tk.Label(
            frame,
            text="Peak percentage : ",
            width=self.label_width,
            anchor="e"
        ).pack(
            side="left"
        )

        self.peak_percentage_entry = tk.Entry(
            frame,
            bg="white",
            width=3,
            validate="all",
            validatecommand=(
                self.register(
                    lambda value: (value.isdigit() or value == "") and len(value) <= 3
                ),
                "%P"
            )
        )
        self.peak_percentage_entry.pack(
            side="left"
        )

        tk.Label(
            frame,
            text="%"
        ).pack(
            side="left"
        )

    def build_peak_distance_setting(self, parent: tk.Frame):
        frame = tk.Frame(
            parent
        )
        frame.pack(
            side='top',
            fill="x"
        )
        tk.Label(
            frame,
            text="Peak distance : ",
            width=self.label_width,
            anchor="e"
        ).pack(
            side="left"
        )

        self.peak_distance_entry = tk.Entry(
            frame,
            bg="white",
            width=3,
            validate="all",
            validatecommand=(
                self.register(
                    lambda value: value.isdigit() or value == ""
                ),
                "%P"
            )
        )
        self.peak_distance_entry.pack(
            side="left"
        )

    # endregion BUILDING SETTINGS

    # endregion BUILDING DETAILS

    # endregion BUILDING HISTOGRAM AND DETAILS

    # endregion BUILDING BODY
    # endregion INTERFACE BUILDING
