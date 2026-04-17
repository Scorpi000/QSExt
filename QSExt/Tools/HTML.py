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


def add_sort_to_html_table(html:str) -> str:
    """
    功能：给 HTML 文件中的所有表格添加点击表头排序功能
    - 自动检测数字列（含百分比、千分位逗号），按数值排序
    - 字符串列按 localeCompare 中文排序
    - 点击表头切换升序/降序，显示箭头指示
    - 与 add_filter_to_html_table 兼容，排序时跳过被筛选隐藏的行
    """
    css = r"""
<style>
/* ====== 表格排序 ====== */
table th.sortable-header {
    cursor: pointer;
    user-select: none;
    position: relative;
    padding-right: 24px !important;
    transition: background-color 0.15s;
}
table th.sortable-header:hover {
    background-color: rgba(0,0,0,0.06) !important;
}
table th.sortable-header .sort-arrow {
    position: absolute;
    right: 6px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 11px;
    opacity: 0.25;
    color: #555;
    line-height: 1;
    pointer-events: none;
}
table th.sortable-header.sort-asc .sort-arrow::after {
    content: "\25B2";
    opacity: 1;
    color: #e74c3c;
}
table th.sortable-header.sort-desc .sort-arrow::after {
    content: "\25BC";
    opacity: 1;
    color: #3498db;
}
</style>
"""

    js = r"""
<script>
(function() {

    function parseNum(text) {
        var s = text.replace(/%/g, '').replace(/,/g, '').replace(/\s/g, '');
        var n = parseFloat(s);
        return isNaN(n) ? null : n;
    }

    function detectNumeric(rows, colIdx) {
        var numCount = 0, total = 0;
        rows.forEach(function(row) {
            var cells = row.querySelectorAll('td');
            var t = (colIdx < cells.length) ? cells[colIdx].textContent.trim() : '';
            if (t === '' || t === '-' || t === '\u2014' || t === 'N/A') return;
            total++;
            if (parseNum(t) !== null) numCount++;
        });
        return (total > 0) && (numCount / total >= 0.8);
    }

    function initSort() {
        document.querySelectorAll('table').forEach(function(table) {
            if (table.dataset.sortInit === '1') return;
            table.dataset.sortInit = '1';

            var thead = table.querySelector('thead');
            if (!thead) return;

            var ths = thead.querySelectorAll('th');
            var tbody = table.querySelector('tbody');

            ths.forEach(function(th, idx) {
                th.classList.add('sortable-header');

                var arrow = document.createElement('span');
                arrow.className = 'sort-arrow';
                th.appendChild(arrow);

                th.addEventListener('click', function() {
                    if (!tbody) return;
                    // 排序时跳过被筛选隐藏的行（.row-hidden）
                    var rows = Array.from(tbody.querySelectorAll('tr:not(.row-hidden)'));
                    if (rows.length === 0) return;

                    var wasAsc = th.classList.contains('sort-asc');
                    ths.forEach(function(h) { h.classList.remove('sort-asc', 'sort-desc'); });
                    var asc = !wasAsc;
                    th.classList.add(asc ? 'sort-asc' : 'sort-desc');

                    var isNum = detectNumeric(rows, idx);

                    rows.sort(function(a, b) {
                        var aCells = a.querySelectorAll('td');
                        var bCells = b.querySelectorAll('td');
                        var aT = (idx < aCells.length) ? aCells[idx].textContent.trim() : '';
                        var bT = (idx < bCells.length) ? bCells[idx].textContent.trim() : '';

                        if (isNum) {
                            var aN = parseNum(aT) || 0;
                            var bN = parseNum(bT) || 0;
                            return asc ? aN - bN : bN - aN;
                        } else {
                            return asc
                                ? aT.localeCompare(bT, 'zh-CN')
                                : bT.localeCompare(aT, 'zh-CN');
                        }
                    });

                    rows.forEach(function(row) { tbody.appendChild(row); });
                });
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSort);
    } else {
        initSort();
    }
})();
</script>
"""

    html = css + "\n" + html + "\n" + js
    return html


def add_filter_to_html_table(html:str) -> str:
    """
    功能：给 HTML 文件中的所有表格添加关键词筛选功能
    - 每个表格上方插入搜索框，实时筛选匹配行
    - 显示筛选计数（显示 N / M 行）
    - 无匹配时提示
    - 与 add_sort_to_html_table 兼容，筛选隐藏行不会干扰排序
    """
    css = r"""
<style>
/* ====== 表格筛选 ====== */
.table-filter-bar {
    margin: 10px 0 6px 0;
    display: flex;
    align-items: center;
    gap: 8px;
}
.table-filter-bar input.filter-input {
    padding: 6px 10px;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 13px;
    width: 260px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.table-filter-bar input.filter-input:focus {
    border-color: #4a90d9;
    box-shadow: 0 0 0 2px rgba(74,144,217,0.18);
}
.table-filter-bar input.filter-input::placeholder {
    color: #aaa;
}
.table-filter-bar .filter-count {
    font-size: 12px;
    color: #888;
    white-space: nowrap;
}
.table-filter-bar .filter-btn-clear {
    font-size: 12px;
    color: #4a90d9;
    cursor: pointer;
    border: none;
    background: none;
    padding: 2px 6px;
    border-radius: 3px;
    display: none;
}
.table-filter-bar .filter-btn-clear:hover {
    background: rgba(74,144,217,0.1);
}
.table-no-match {
    display: none;
    text-align: center;
    color: #999;
    padding: 12px;
    font-size: 13px;
}
/* 被筛选隐藏的行（排序脚本通过 :not(.row-hidden) 跳过） */
table tbody tr.row-hidden {
    display: none;
}
</style>
"""

    js = r"""
<script>
(function() {

    function initFilter() {
        document.querySelectorAll('table').forEach(function(table) {
            if (table.dataset.filterInit === '1') return;
            table.dataset.filterInit = '1';

            var tbody = table.querySelector('tbody');
            if (!tbody) return;

            // 创建筛选栏
            var bar = document.createElement('div');
            bar.className = 'table-filter-bar';
            bar.innerHTML =
                '<span style="font-size:14px;color:#999;">\u{1F50D}</span>' +
                '<input class="filter-input" type="text" placeholder="\u7B5B\u9009\u5173\u952E\u8BCD\u2026" />' +
                '<span class="filter-count"></span>' +
                '<button class="filter-btn-clear" title="\u6E05\u9664">\u2715</button>';
            table.parentNode.insertBefore(bar, table);

            // 无匹配提示
            var noMatch = document.createElement('div');
            noMatch.className = 'table-no-match';
            noMatch.textContent = '\u6CA1\u6709\u5339\u914D\u7684\u884C';
            table.parentNode.insertBefore(noMatch, table.nextSibling);

            var input    = bar.querySelector('.filter-input');
            var countEl  = bar.querySelector('.filter-count');
            var clearBtn = bar.querySelector('.filter-btn-clear');

            function applyFilter() {
                var keyword = input.value.trim().toLowerCase();
                var allRows = tbody.querySelectorAll('tr');
                var total   = allRows.length;
                var visible = 0;

                if (!keyword) {
                    allRows.forEach(function(r) { r.classList.remove('row-hidden'); });
                    noMatch.style.display = 'none';
                } else {
                    allRows.forEach(function(row) {
                        var text  = (row.textContent || '').toLowerCase();
                        var match = text.indexOf(keyword) !== -1;
                        row.classList.toggle('row-hidden', !match);
                        if (match) visible++;
                    });
                    noMatch.style.display = visible === 0 ? 'block' : 'none';
                }

                countEl.textContent = keyword
                    ? '\u663E\u793A ' + visible + ' / ' + total + ' \u884C'
                    : '';
                clearBtn.style.display = keyword ? 'inline-block' : 'none';
            }

            input.addEventListener('input', applyFilter);

            clearBtn.addEventListener('click', function() {
                input.value = '';
                applyFilter();
                input.focus();
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFilter);
    } else {
        initFilter();
    }
})();
</script>
"""

    html = css + "\n" + html + "\n" + js
    return html
