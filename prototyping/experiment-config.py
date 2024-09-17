import json
import pandas as pd
import os

class ExperimentConf:
    """
    A class to dynamically generate and store parameters loaded from a JSON file.
    """

    def __init__(self):
        """
        Initialize the ExperimentParameters class.
        """
        self._parameters = {}
        self._dataframe = pd.DataFrame()
        self._output_path = ''

    def load_parameters(self, json_file_path):
        """
        Load parameters from a JSON file.

        Parameters:
        json_file_path (str): Path to the JSON file containing experiment parameters.
        """
        try:
            with open(json_file_path, 'r') as f:
                self._parameters = json.load(f)
        except FileNotFoundError:
            print(f"File not found: {json_file_path}")
            return
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return

        # Update the dataframe
        self._dataframe = pd.DataFrame([self._parameters])

        # Update the output path
        self._create_bids_output_path()

    def _create_bids_output_path(self):
        """
        Create a BIDS-formatted output path based on the loaded parameters.
        """
        # Implement logic to create BIDS formatted output path
        # For example, BIDS output path can be constructed using subject, session, task, etc.
        subject = self._parameters.get('subject', 'unknown')
        session = self._parameters.get('session', 'unknown')
        task = self._parameters.get('task', 'unknown')

        # Construct the directory path
        directory_path = os.path.join(
            f"sub-{subject}",
            f"ses-{session}",
            'func'
        )

        # Construct the filename
        filename = f"sub-{subject}_ses-{session}_task-{task}_bold.nii.gz"

        # Combine directory and filename
        self._output_path = os.path.join(directory_path, filename)

    @property
    def parameters(self):
        """
        Get the parameters dictionary.

        Returns:
        dict: Dictionary containing the experiment parameters.
        """
        return self._parameters

    @property
    def dataframe(self):
        """
        Get the parameters as a pandas DataFrame.

        Returns:
        pandas.DataFrame: DataFrame containing the experiment parameters.
        """
        return self._dataframe

    @property
    def output_path(self):
        """
        Get the BIDS-formatted output path.

        Returns:
        str: BIDS-formatted output path.
        """
        return self._output_path

    def update_parameter(self, key, value):
        """
        Update a specific parameter.

        Parameters:
        key (str): The parameter key to update.
        value: The new value for the parameter.
        """
        self._parameters[key] = value
        # Update the dataframe
        self._dataframe[key] = [value]
        # Update the output path in case relevant parameters have changed
        if key in ['subject', 'session', 'task']:
            self._create_bids_output_path()

    def reload_parameters(self, json_file_path):
        """
        Reload parameters from a new JSON file.

        Parameters:
        json_file_path (str): Path to the new JSON file.
        """
        self.load_parameters(json_file_path)


# GUI application to interact with the ExperimentParameters class

import sys
import os
import json
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QMessageBox, QLabel, QHeaderView
)
from PyQt5.QtCore import Qt


class ExperimentParametersGUI(QWidget):
    """
    A GUI interface for the ExperimentParameters class that allows loading a JSON file,
    displaying parameters in a table, and editing them dynamically.
    """

    def __init__(self):
        super().__init__()
        self.exp_params = ExperimentConf()
        self.init_ui()

    def init_ui(self):
        """
        Initialize the user interface.
        """
        self.setWindowTitle('Experiment Parameters GUI')
        self.setGeometry(100, 100, 600, 400)

        layout = QVBoxLayout()

        # Load JSON button
        self.load_button = QPushButton('Load JSON File')
        self.load_button.clicked.connect(self.load_json)
        layout.addWidget(self.load_button)

        # Parameters table
        self.table = QTableWidget()
        self.table.itemChanged.connect(self.update_parameters_from_table)
        layout.addWidget(self.table)

        # BIDS-formatted output path label
        self.output_path_label = QLabel('BIDS-formatted Output Path: ')
        layout.addWidget(self.output_path_label)

        self.setLayout(layout)

    def load_json(self):
        """
        Open a file dialog to select a JSON file and load the parameters.
        """
        options = QFileDialog.Options()
        json_file, _ = QFileDialog.getOpenFileName(
            self, "Open JSON File", "", "JSON Files (*.json);;All Files (*)", options=options
        )
        if json_file:
            self.exp_params.load_parameters(json_file)
            if self.exp_params.parameters:
                self.populate_table()
                self.update_output_path_label()
            else:
                QMessageBox.warning(self, 'Error', 'Failed to load parameters from the file.')

    def populate_table(self):
        """
        Populate the table with parameters from the DataFrame.
        """
        df = self.exp_params.dataframe
        self.table.blockSignals(True)  # Prevent signals while updating the table

        self.table.setRowCount(df.shape[0])
        self.table.setColumnCount(df.shape[1])
        self.table.setHorizontalHeaderLabels(df.columns.tolist())
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        for row in range(df.shape[0]):
            for col, key in enumerate(df.columns):
                value = df.iloc[row, col]
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.table.setItem(row, col, item)

        self.table.blockSignals(False)  # Re-enable signals

    def update_parameters_from_table(self, item):
        """
        Update the ExperimentParameters instance when a table item is changed.
        """
        key = self.table.horizontalHeaderItem(item.column()).text()
        value = item.text()

        # Update the parameter in the class
        self.exp_params.update_parameter(key, value)

        # Update the output path label if relevant parameters have changed
        if key in ['subject', 'session', 'task']:
            self.update_output_path_label()

    def update_output_path_label(self):
        """
        Update the label displaying the BIDS-formatted output path.
        """
        self.output_path_label.setText(f"BIDS-formatted Output Path: {self.exp_params.output_path}")

def main():
    app = QApplication(sys.argv)
    gui = ExperimentParametersGUI()
    gui.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
