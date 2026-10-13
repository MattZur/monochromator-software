import sys
import threading
import time
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QComboBox
)
from PySide6.QtCore import Qt
import monochrom_control_code_draft as mchrom

class DegreeControl(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Degree Controller")
        self.value = 0.0  # Current position
        self.saved_positions = []  # List to store saved positions

        # Labels: Current position
        self.angle_label = QLabel(f"{self.value:.2f}°")
        self.angle_label.setStyleSheet("font-size: 24px;")
        self.angle_label.setAlignment(Qt.AlignCenter)

        # Layouts
        main_layout = QVBoxLayout()
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.angle_label)

        # Save position button
        self.save_button = QPushButton("Save Position")
        self.save_button.clicked.connect(self.save_position)

        # Dropdown for saved positions
        self.position_dropdown = QComboBox()

        # Go to saved position button
        self.goto_saved_button = QPushButton("Go to Selected")
        self.goto_saved_button.clicked.connect(self.goto_saved_position)

        # Add save + dropdown + go buttons
        status_layout.addWidget(self.save_button)
        status_layout.addWidget(self.position_dropdown)
        status_layout.addWidget(self.goto_saved_button)

        # Row for 1 degree
        row1 = QHBoxLayout()
        row1.addWidget(self.create_button("-1°", -1))
        row1.addWidget(self.create_button("+1°", 1))

        # Row for 0.1 degree
        row2 = QHBoxLayout()
        row2.addWidget(self.create_button("-0.1°", -0.1))
        row2.addWidget(self.create_button("+0.1°", 0.1))

        # Row for 0.01 degree
        row3 = QHBoxLayout()
        row3.addWidget(self.create_button("-0.01°", -0.01))
        row3.addWidget(self.create_button("+0.01°", 0.01))

        # Manual input for delta movement with + and - buttons
        input_layout = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("Enter Step Size")
        self.plus_button = QPushButton("+")
        self.minus_button = QPushButton("-")
        self.plus_button.clicked.connect(lambda: self.move_manual(True))
        self.minus_button.clicked.connect(lambda: self.move_manual(False))
        input_layout.addWidget(self.input_box)
        input_layout.addWidget(self.minus_button)
        input_layout.addWidget(self.plus_button)


        # Add everything to main layout
        main_layout.addLayout(status_layout)
        main_layout.addLayout(row1)
        main_layout.addLayout(row2)
        main_layout.addLayout(row3)
        main_layout.addLayout(input_layout)

        self.setLayout(main_layout)

        # Start a thread to update current position
        threading.Thread(target=self.update_status_loop, daemon=True).start()

    def create_button(self, text, delta):
        button = QPushButton(text)
        button.clicked.connect(lambda: self.change_value(delta))
        return button

    def change_value(self, delta):
        def move():
            mchrom.step(delta)
        threading.Thread(target=move, daemon=True).start()

    def move_manual(self, positive=True):
        text = self.input_box.text()
        try:
            delta = float(text)
        except ValueError:
            return  # do nothing if input is invalid

        if delta <= 0:
            return  # ignore zero or negative typed values

        if not positive:
            delta = -delta

        # Calculate safe delta to stay within limits
        current_pos = mchrom.userdefined_current_position()
        if current_pos + delta > 15:
            delta = 15 - current_pos
        elif current_pos + delta < -15:
            delta = -15 - current_pos

        if delta == 0:
            return  # already at limit

        def move():
            mchrom.step(delta)
        threading.Thread(target=move, daemon=True).start()

    def save_position(self):
        pos = mchrom.userdefined_current_position()
        self.saved_positions.append(pos)
        self.position_dropdown.addItem(f"{pos:.2f}°")

    def goto_saved_position(self):
        index = self.position_dropdown.currentIndex()
        if index == -1:
            return  # no selection
        target = self.saved_positions[index]

        def move():
            mchrom.goTo(target)
        threading.Thread(target=move, daemon=True).start()

    def update_status_loop(self):
        while True:
            self.value = mchrom.userdefined_current_position()
            self.angle_label.setText(f"{self.value:.2f}°")
            time.sleep(0.1)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DegreeControl()
    window.show()
    sys.exit(app.exec())