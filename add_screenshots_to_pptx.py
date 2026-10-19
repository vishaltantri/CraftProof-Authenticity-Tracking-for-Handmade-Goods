#!/usr/bin/env python3
"""
Add workflow screenshots from WORKFLOW_GUIDE.md as new slides in the PPTX.
"""
import re
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# Paths
PPTX_PATH = Path("/home/vct/Downloads/cleaned_CraftProof-Authenticity-Tracking-for-Handmade-Goods.pptx")
OUTPUT_PATH = Path("/home/vct/crypto/cleaned_CraftProof-Authenticity-Tracking-for-Handmade-Goods_with_screenshots.pptx")
SCREENSHOTS_DIR = Path("/home/vct/crypto/craftproof/docs/screenshots")
MD_PATH = Path("/home/vct/Downloads/WORKFLOW_GUIDE.md")

def parse_workflow_guide(md_path):
    """Parse the markdown to extract screenshot references with context."""
    content = md_path.read_text()
    
    # Split by parts and steps
    # Pattern: ## Part X — Title, ### Step N · Title, ![Alt](path)
    parts = []
    current_part = None
    current_step = None
    
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Part heading
        part_match = re.match(r'^##\s+Part\s+\d+\s*[—\-]\s*(.+)$', line)
        if part_match:
            current_part = part_match.group(1).strip()
            current_step = None
            parts.append({"type": "part", "title": current_part, "steps": []})
            i += 1
            continue
        
        # Step heading
        step_match = re.match(r'^###\s+Step\s+(\d+)\s*[·\.\-]\s*(.+)$', line)
        if step_match and current_part is not None:
            step_num = int(step_match.group(1))
            step_title = step_match.group(2).strip()
            current_step = {"number": step_num, "title": step_title, "description": [], "screenshots": []}
            parts[-1]["steps"].append(current_step)
            i += 1
            continue
        
        # Screenshot reference
        img_match = re.match(r'^!\[([^\]]*)\]\((screenshots/[^)]+)\)', line)
        if img_match and current_step is not None:
            alt_text = img_match.group(1)
            img_path = img_match.group(2)
            current_step["screenshots"].append({
                "alt": alt_text,
                "path": img_path,
                "filename": Path(img_path).name
            })
            i += 1
            continue
        
        # Collect description text for current step
        if current_step is not None and line.strip() and not line.startswith('#') and not line.startswith('![') and not line.startswith('```') and not line.startswith('---'):
            # Skip table rows and code blocks
            if not line.strip().startswith('|') and not line.strip().startswith('`'):
                current_step["description"].append(line.strip())
        
        i += 1
    
    return parts

def add_screenshot_slides(prs, parts, screenshots_dir):
    """Add new slides for each screenshot."""
    
    # Get slide dimensions
    slide_width = prs.slide_width
    slide_height = prs.slide_height
    
    # Use a blank slide layout (index 0 = DEFAULT)
    blank_layout = prs.slide_layouts[0]
    
    for part in parts:
        # Add a part divider slide
        slide = prs.slides.add_slide(blank_layout)
        add_part_divider(slide, part["title"], slide_width, slide_height)
        
        for step in part["steps"]:
            for idx, screenshot in enumerate(step["screenshots"]):
                img_path = screenshots_dir / screenshot["filename"]
                if not img_path.exists():
                    print(f"Warning: Screenshot not found: {img_path}")
                    continue
                
                slide = prs.slides.add_slide(blank_layout)
                add_screenshot_slide(
                    slide, 
                    step["number"], 
                    step["title"], 
                    screenshot["alt"], 
                    img_path,
                    part["title"],
                    slide_width, 
                    slide_height
                )
                print(f"Added slide for Step {step['number']}: {screenshot['alt']}")

def add_part_divider(slide, part_title, slide_width, slide_height):
    """Add a part divider slide."""
    # Background
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(0x1a, 0x1a, 0x2e)  # Dark navy
    
    # Part label
    txBox = slide.shapes.add_textbox(
        Inches(1), Inches(2.5), Inches(8), Inches(1.5)
    )
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "WORKFLOW WALKTHROUGH"
    p.font.size = Pt(24)
    p.font.color.rgb = RGBColor(0x00, 0xd4, 0xff)  # Cyan accent
    p.font.bold = True
    p.alignment = PP_ALIGN.CENTER
    
    # Part title
    txBox2 = slide.shapes.add_textbox(
        Inches(1), Inches(4), Inches(8), Inches(2)
    )
    tf2 = txBox2.text_frame
    tf2.word_wrap = True
    p2 = tf2.paragraphs[0]
    p2.text = part_title
    p2.font.size = Pt(40)
    p2.font.color.rgb = RGBColor(0xff, 0xff, 0xff)
    p2.font.bold = True
    p2.alignment = PP_ALIGN.CENTER

def add_screenshot_slide(slide, step_num, step_title, alt_text, img_path, part_title, slide_width, slide_height):
    """Add a slide with screenshot and context."""
    # Background - light
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor(0xf8, 0xf9, 0xfa)
    
    # Header bar
    from pptx.util import Emu
    header_shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE.RECTANGLE
        Emu(0), Emu(0), slide_width, Inches(1.1)
    )
    header_shape.fill.solid()
    header_shape.fill.fore_color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
    header_shape.line.fill.background()
    
    # Step label in header
    txBox = slide.shapes.add_textbox(
        Inches(0.5), Inches(0.15), Inches(6), Inches(0.8)
    )
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = f"Part: {part_title}  •  Step {step_num}"
    p.font.size = Pt(16)
    p.font.color.rgb = RGBColor(0x00, 0xd4, 0xff)
    p.font.bold = True
    
    # Step title
    txBox2 = slide.shapes.add_textbox(
        Inches(0.5), Inches(1.3), Inches(9), Inches(0.7)
    )
    tf2 = txBox2.text_frame
    tf2.word_wrap = True
    p2 = tf2.paragraphs[0]
    p2.text = step_title
    p2.font.size = Pt(24)
    p2.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
    p2.font.bold = True
    
    # Add screenshot - center it, max width 9 inches, max height 5 inches
    max_width = Inches(9)
    max_height = Inches(5)
    
    # Add picture
    pic = slide.shapes.add_picture(
        str(img_path),
        Inches(0.5), Inches(2.1),
        width=max_width,
        height=max_height
    )
    
    # Center the image horizontally
    pic.left = int((slide_width - pic.width) / 2)
    
    # Caption below image
    caption_top = pic.top + pic.height + Inches(0.2)
    if caption_top < slide_height - Inches(1):
        txBox3 = slide.shapes.add_textbox(
            Inches(1), caption_top, Inches(8), Inches(0.6)
        )
        tf3 = txBox3.text_frame
        tf3.word_wrap = True
        p3 = tf3.paragraphs[0]
        p3.text = alt_text
        p3.font.size = Pt(14)
        p3.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        p3.font.italic = True
        p3.alignment = PP_ALIGN.CENTER

def main():
    print("Loading PPTX...")
    prs = Presentation(PPTX_PATH)
    print(f"Original slides: {len(prs.slides)}")
    
    print("Parsing workflow guide...")
    parts = parse_workflow_guide(MD_PATH)
    
    print("Adding screenshot slides...")
    add_screenshot_slides(prs, parts, SCREENSHOTS_DIR)
    
    print(f"Total slides after: {len(prs.slides)}")
    
    print(f"Saving to {OUTPUT_PATH}...")
    prs.save(OUTPUT_PATH)
    print("Done!")

if __name__ == "__main__":
    main()