# -*- coding: utf-8 -*-
from html.parser import HTMLParser


class TableHTMLParser(HTMLParser):
    """HTML表格解析器"""
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tr = False
        self.in_cell = False
        self.current_cell_content = []
        self.current_row = []
        self.rows = []
        self.cell_type = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
            self.rows = []
        elif tag == 'tr':
            self.in_tr = True
            self.current_row = []
        elif tag in ['th', 'td']:
            self.in_cell = True
            self.cell_type = tag
            self.current_cell_content = []

    def handle_endtag(self, tag):
        if tag == 'table':
            self.in_table = False
        elif tag == 'tr':
            self.in_tr = False
            if self.current_row:
                self.rows.append(self.current_row)
        elif tag in ['th', 'td']:
            self.in_cell = False
            cell_content = ''.join(self.current_cell_content).strip()
            self.current_row.append(cell_content)

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell_content.append(data)

    def get_rows(self):
        return self.rows
