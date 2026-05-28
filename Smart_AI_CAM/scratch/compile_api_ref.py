import os
import re
import stat
from html.parser import HTMLParser

class HTMLToMarkdownParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.output = []
        self.in_table = False
        self.in_tr = False
        self.in_th = False
        self.in_td = False
        self.in_pre = False
        self.in_code = False
        self.in_nav = False
        self.in_style = False
        self.in_script = False
        self.table_cols = 0
        self.table_headers = []
        self.table_row = []
        self.table_rows = []
        self.current_href = None
        self.li_level = 0
        self.in_div_box = False
        self.in_div_muted = False
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        # Style and script tags - skip entirely
        if tag == 'style':
            self.in_style = True
            return
        if tag == 'script':
            self.in_script = True
            return
            
        # Navigation bar detection - skip the navigation links
        if tag == 'div' and attrs_dict.get('class') == 'nav':
            self.in_nav = True
            return
            
        if self.in_nav or self.in_style or self.in_script:
            return
            
        if tag == 'a':
            self.current_href = attrs_dict.get('href')
            
        elif tag == 'h1':
            self.output.append("\n# ")
        elif tag == 'h2':
            self.output.append("\n## ")
        elif tag == 'h3':
            self.output.append("\n### ")
        elif tag == 'p':
            self.output.append("\n")
        elif tag == 'div' and attrs_dict.get('class') == 'box':
            self.in_div_box = True
            self.output.append("\n> [!IMPORTANT]\n> ")
        elif tag == 'div' and attrs_dict.get('class') == 'muted':
            self.in_div_muted = True
            self.output.append("\n> [!NOTE]\n> ")
        elif tag == 'pre':
            self.in_pre = True
            self.output.append("\n```python\n")
        elif tag == 'code':
            self.in_code = True
            if not self.in_pre:
                self.output.append("`")
        elif tag == 'table':
            self.in_table = True
            self.table_rows = []
            self.table_headers = []
        elif tag == 'tr':
            self.in_tr = True
            self.table_row = []
        elif tag == 'th':
            self.in_th = True
        elif tag == 'td':
            self.in_td = True
        elif tag == 'ul':
            self.li_level += 1
        elif tag == 'li':
            self.output.append("\n" + "  " * (self.li_level - 1) + "- ")
            
    def handle_endtag(self, tag):
        if tag == 'style':
            self.in_style = False
            return
        if tag == 'script':
            self.in_script = False
            return
            
        if tag == 'div' and self.in_nav:
            self.in_nav = False
            return
            
        if self.in_nav or self.in_style or self.in_script:
            return
            
        if tag == 'a':
            self.current_href = None
        elif tag in ['h1', 'h2', 'h3']:
            self.output.append("\n")
        elif tag == 'p':
            self.output.append("\n")
        elif tag == 'div' and self.in_div_box:
            self.in_div_box = False
            self.output.append("\n")
        elif tag == 'div' and self.in_div_muted:
            self.in_div_muted = False
            self.output.append("\n")
        elif tag == 'pre':
            self.in_pre = False
            self.output.append("```\n")
        elif tag == 'code':
            self.in_code = False
            if not self.in_pre:
                self.output.append("`")
        elif tag == 'th':
            self.in_th = False
        elif tag == 'td':
            self.in_td = False
        elif tag == 'tr':
            self.in_tr = False
            if self.in_table:
                if self.table_headers and not self.table_rows and len(self.table_row) == len(self.table_headers):
                    # We processed header row
                    pass
                else:
                    self.table_rows.append(self.table_row)
        elif tag == 'table':
            self.in_table = False
            # Render Markdown table
            if self.table_headers:
                self.output.append("\n| " + " | ".join(self.table_headers) + " |\n")
                self.output.append("| " + " | ".join(["---"] * len(self.table_headers)) + " |\n")
                for row in self.table_rows:
                    row_padded = row + [""] * (len(self.table_headers) - len(row))
                    self.output.append("| " + " | ".join(row_padded) + " |\n")
            elif self.table_rows:
                num_cols = max(len(r) for r in self.table_rows)
                headers = [f"Column {i+1}" for i in range(num_cols)]
                self.output.append("\n| " + " | ".join(headers) + " |\n")
                self.output.append("| " + " | ".join(["---"] * num_cols) + " |\n")
                for row in self.table_rows:
                    row_padded = row + [""] * (num_cols - len(row))
                    self.output.append("| " + " | ".join(row_padded) + " |\n")
            self.output.append("\n")
        elif tag == 'ul':
            self.li_level -= 1
            if self.li_level == 0:
                self.output.append("\n")
                
    def handle_data(self, data):
        if self.in_nav or self.in_style or self.in_script:
            return
            
        if self.in_pre:
            self.output.append(data)
        elif self.in_th:
            self.table_headers.append(data.strip().replace("\n", " ").replace("|", "\\|"))
        elif self.in_td:
            cell_str = data.strip().replace("\n", " ").replace("|", "\\|")
            self.table_row.append(cell_str)
        else:
            cleaned = data.replace("\n", " ").strip()
            if cleaned:
                if self.current_href:
                    self.output.append(f" [{cleaned}]({self.current_href}) ")
                else:
                    if self.in_div_box or self.in_div_muted:
                        cleaned = cleaned.replace("  ", " ")
                        self.output.append(cleaned)
                    else:
                        self.output.append(cleaned)

def parse_html_to_markdown(html_content):
    parser = HTMLToMarkdownParser()
    parser.feed(html_content)
    text = "".join(parser.output)
    
    # Post processing cleanup
    text = re.sub(r'\n{3,}', '\n\n', text) # Remove excessive newlines
    text = re.sub(r' +', ' ', text)       # Remove multiple consecutive spaces
    text = re.sub(r'` +', '`', text)
    text = re.sub(r' +`', '`', text)
    return text

def heal_mojibake(content):
    """Heal the double-encoded UTF-8 to Latin-1 Mojibake."""
    try:
        # First check if there is any Mojibake character pattern
        # Encoding as latin-1 and decoding as utf-8 resolves the issue
        return content.encode('latin-1').decode('utf-8')
    except Exception:
        # Fallback if there is an error in encoding/decoding
        return content

def main():
    base_dir = r"E:\Fusion\插件\Smart_AI_CAM\docs\fusion_api_reference"
    output_path = r"E:\Fusion\插件\Smart_AI_CAM\docs\FUSION_API_DATABASE.md"
    
    files_sequence = [
        ("reference.html", "Fusion API 參考手冊"),
        ("reference_cam_methods.html", "CAM Methods 全表"),
        ("reference_design_api.html", "設計 API (BRepBody/Face/Sketch)"),
        ("reference_cam_api.html", "CAM Parameter API (官方完整)"),
        ("reference_setup_operation.html", "Setup & Operation API (官方完整)"),
        ("reference_cam_core.html", "CAM Core API (CAM/Setups/Operations/ToolLib/PostProcess)"),
        ("reference_machine_template.html", "Machine / CAMTemplate / NCProgram API"),
        ("reference_manufacturing_overview.html", "製造 API 功能總覽"),
        ("reference_recognition.html", "特徵辨識 API (孔/口袋/PocketRecognitionSelection)"),
        ("reference_geometry_selection.html", "幾何選取 API (CurveSelections/Chain/Silhouette/Sketch)"),
        ("reference_tool_preset.html", "工具 / ToolPreset / SetupGroup API"),
        ("reference_additive_export.html", "Additive / Export / PrintSetting API")
    ]
    
    if os.path.exists(output_path):
        os.chmod(output_path, stat.S_IWRITE)
        
    db_content = []
    db_content.append("<!-- [SYSTEM: READ-ONLY] -->")
    db_content.append("# 🛠️ Autodesk Fusion 360 CAM/Design Official API Reference Database")
    db_content.append("> [!IMPORTANT]")
    db_content.append("> **本資料庫為官方 API 與最佳實踐的「唯讀/禁止變更」核心資料庫**。用於提供 AI 助理最精確的程式碼參考。請勿手動修改此檔案內容。")
    db_content.append("")
    db_content.append("## 📌 快速索引目錄")
    for idx, (filename, title) in enumerate(files_sequence):
        anchor = title.lower().replace(" ", "-").replace("/", "").replace("(", "").replace(")", "").replace("&", "")
        db_content.append(f"{idx+1}. [{title}](#{anchor})")
    db_content.append("\n---\n")
    
    for filename, title in files_sequence:
        file_path = os.path.join(base_dir, filename)
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            continue
            
        print(f"Parsing and healing: {filename}...")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_content = f.read()
            
        # Heal Mojibake
        healed_content = heal_mojibake(raw_content)
        
        markdown_sec = parse_html_to_markdown(healed_content)
        
        # Add custom anchor/header
        anchor_name = title.lower().replace(' ', '-').replace('/', '').replace('(', '').replace(')', '').replace('&', '')
        db_content.append(f"\n<a name=\"{anchor_name}\"></a>")
        db_content.append(f"## 📚 {title}")
        db_content.append(markdown_sec)
        db_content.append("\n\n---\n")
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(db_content))
        
    print(f"Successfully generated clean database at: {output_path}")
    
    # Mark file as Read-Only
    os.chmod(output_path, stat.S_IREAD)
    print("Marked FUSION_API_DATABASE.md as Read-Only.")

if __name__ == "__main__":
    main()
