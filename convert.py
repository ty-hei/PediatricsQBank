import re
import json
import hashlib
import os

# =================配置区域=================
# 输入文件列表 (按顺序合并)
INPUT_FILES = ['Q1.md', 'Q2.md'] 
OUTPUT_DIR = 'dist'
OUTPUT_HTML = 'index.html'
DOMAIN = "https://PediatricsQBank.heihaheihaha.com"
# DOMAIN = "" # Use relative path for API calls
# =========================================

def generate_hash_id(text):
    """生成的ID仅依赖题目文本内容，确保题目顺序调整不影响历史记录"""
    clean_text = re.sub(r'\s+', '', text)
    return hashlib.md5(clean_text.encode('utf-8')).hexdigest()[:12]

def finalize_question(q):
    if not q: return None
    
    # --- Short Answer Split Logic ---
    match_sa = re.match(r'^(.*?[。？!])\s+(.*[\u4e00-\u9fa5].*)$', q["title"])
    if match_sa:
        title_part = match_sa.group(1)
        ans_part = match_sa.group(2)
        if "意识：" in ans_part or "分）" in ans_part or "分)" in ans_part:
             q["title"] = title_part
             q["analysis"] = ans_part
             q["type"] = "mix"
    # --------------------------------

    full_content = q['title'] + "".join([o['text'] for o in q['options']])
    q['id'] = generate_hash_id(full_content)
    
    # Heuristic: If no options are present, it is effectively a Short Answer / Essay
    if not q['options'] and q.get('type') == 'single':
        q['type'] = 'mix'

    return q

# The original parse_simple_markdown and parse_q2_markdown are replaced by convert_to_json
# based on the provided code edit.

# 正则预编译
re_chapter = re.compile(r'^#\s+(.*)')
re_question_start = re.compile(r'^(\d+)[\.．]\s*(.*)')
re_option = re.compile(r'^\s*([A-F])[:\.\、]\s*(.*)')
re_answer = re.compile(r'^\s*(?:参考)?答案[:：]\s*([A-Z, ]+)')
re_analysis = re.compile(r'^\s*解析[:：]\s*(.*)')
re_case_q_start = re.compile(r'^(\d+)[\.．]\s*(.*)')
# New: Group Header for Type B (Shared Options) or Type A3/A4 (Shared Stem)
# Matches: "5~6题共用备选答案" or "30～31题干" or "$50\sim 54$题..."
re_group_header = re.compile(r'^\s*\$?(\d+)\s*(?:[~～-]|\\sim)\s*\$?(\d+)\s*.*(?:题)?(?:共用)?(备选答案|题干).*')


def convert_to_json(md_files):
    # Local Regex Definitions to avoid scope issues
    re_inline_opt = re.compile(r'([A-G])[:\.\、]\s*(.*?)(?=\s*[A-G][:\.\、]|\s*您的答案|\s*正确答案|$)', re.DOTALL)
    re_ans_tail = re.compile(r'\s*(?:您的答案.*)?(?:正确)?答案(?:是)?[:：]\s*([A-Z]+)', re.IGNORECASE)
    re_full_ans_line = re.compile(r'^\s*(?:您的答案.*)?(?:正确)?(?:参考)?答案(?:是)?[:：]\s*([A-Z, ]+)', re.IGNORECASE)

    all_chapters = []
    
    for f_path in md_files:
        print(f"Processing {f_path}...")
        if not os.path.exists(f_path):
            print(f"Warning: {f_path} not found.")
            continue

        with open(f_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        current_chapter = None
        current_q = None
        in_noun_exp = False
        in_case_analysis = False
        in_requirements = False # New state for Teaching Objectives
        in_ref_answers = False # New state for Reference Answers

        # Group Context State
        group_info = {
            'active': False,
            'start': 0,
            'end': 0,
            'type': '', # 'options' or 'stem'
            'data': [], # list of opts for 'options', string for 'stem'
            'stem_text': '' 
        }

        def finalize_question(q):
            if not q: return None

            # --- Short Answer Split Logic ---
            match_sa = re.match(r'^(.*?[。？!])\s+(.*[\u4e00-\u9fa5].*)$', q["title"])
            # Only apply if it looks like a Short Answer (no options yet) and has long trailing text
            if match_sa and not q['options']:
                title_part = match_sa.group(1)
                ans_part = match_sa.group(2)
                # Heuristic to ensure we don't split titles that just have punctuation
                if "意识：" in ans_part or "分）" in ans_part or "分)" in ans_part or len(ans_part) > 10:
                    q["title"] = title_part
                    q["analysis"] = ans_part + "\n" + q["analysis"]
                    q["type"] = "mix"
            # --------------------------------

            # If Q is within active group range, apply group data
            if group_info['active'] and q.get('seq'):
                try:
                    # Seq might be "5" or "5." or "119"
                    seq = int(q['seq'])
                    if group_info['start'] <= seq <= group_info['end']:
                        # Apply Shared Options
                        if group_info['type'] == 'options' and not q['options']:
                            # Copied list of options
                            q['options'] = [o.copy() for o in group_info['data']]
                            # Assign Group ID for frontend rendering
                            # Generate deterministic hash based on options content
                            opt_str = json.dumps(group_info['data'], sort_keys=True)
                            q['group_id'] = hashlib.md5(opt_str.encode('utf-8')).hexdigest()[:8]
                            
                            if q['type'] == 'essay': q['type'] = 'single' # Assume single/multi if options exist
                        
                        # Apply Shared Stem
                        elif group_info['type'] == 'stem':
                            q['title'] =  f"(题干) {group_info['stem_text']}\n\n{q['title']}"
                except ValueError: 
                    pass
            
            # Post-process Type
            if q['options']:
                q['type'] = 'single'
                if q['answer'] and len(q['answer']) > 1: q['type'] = 'multi'
            elif q['type'] == 'single':
                q['type'] = 'mix' # Default to mix if no options

            # Generate ID
            full_content = q['title'] + "".join([o['text'] for o in q['options']])
            q['id'] = generate_hash_id(full_content)

            return q

        # Ensure default chapter exists if needed
        if not all_chapters and (not lines or not lines[0].strip().startswith('#')):
            current_chapter = {"title": f"文档 {f_path}", "questions": [], "desc": ""}
            all_chapters.append(current_chapter)
        elif all_chapters and (not lines or not lines[0].strip().startswith('#')):
            current_chapter = all_chapters[-1]

        for line in lines:
            line = line.strip()
            if not line: continue
            
            # --- Teaching Requirements Mode ---
            if in_requirements:
                 if line.startswith('# '):
                      if "复习题" in line or any(k in line for k in ["选择题", "简答题"]):
                           in_requirements = False
                           # Fall through to normal processing to handle the new section header
                      elif "教学要求" in line or "【" in line or "（" in line:
                           # Ignore inner headers like # 【教学目的】 or # （一）
                           continue
                      else:
                           # Weird header found? Exit mode just in case
                           in_requirements = False
                 
                 # If still in requirements, append text to Desc
                 if in_requirements:
                      if "desc" not in current_chapter: current_chapter["desc"] = ""
                      current_chapter["desc"] += line + "<br>"
                      continue
            # ----------------------------------

            # --- Noun Explanation Mode ---
            if in_noun_exp:
                if line.startswith('# '):
                   if any(k in line for k in ["简答题", "病例分析", "问答题", "选择题", "复习题"]):
                       in_noun_exp = False
                   else:
                        if current_q:
                            finalize_question(current_q)
                            current_chapter["questions"].append(current_q)
                        
                        term = line.replace('#', '').strip()
                        current_q = {
                            "id": "",
                            "seq": "",
                            "title": term,
                            "options": [],
                            "answer": "见解析",
                            "analysis": "",
                            "type": "essay"
                        }
                        continue
                else:
                    if current_q: current_q["analysis"] += line + "\n"
                    continue
            # -----------------------------
            
            # --- Case Analysis Mode ---
            if in_case_analysis:
                 if line.startswith('# '):
                      if any(k in line for k in ["选择题", "复习题"]):
                           in_case_analysis = False
                 else:
                      match_cq = re_case_q_start.match(line)
                      # Check if it looks like a new question (and not validation text)
                      if match_cq and not line.startswith('答') and "答案" not in line[:5]: 
                          # FIX: Check if it's a valid next question (must be sequential)
                          # If we have a current question, ensure the new one is greater.
                          is_valid_new_q = True
                          if current_q and current_q.get('seq'):
                              try:
                                  curr_seq = int(current_q['seq'])
                                  new_seq = int(match_cq.group(1))
                                  # If new sequence is not greater, it's likely a list item in the answer/analysis
                                  if new_seq <= curr_seq:
                                      is_valid_new_q = False
                              except ValueError:
                                  pass # If seq is not int, safely ignore and assume valid
                          
                          if is_valid_new_q:
                               if current_q:
                                  finalize_question(current_q)
                                  current_chapter["questions"].append(current_q)
                               
                               current_q = {
                                   "id": "",
                                   "seq": match_cq.group(1),
                                   "title": match_cq.group(2),
                                   "options": [],
                                   "answer": "",
                                   "analysis": "",
                                   "type": "case" 
                               }
                               continue

                      
                      # Append to Analysis or Title
                      if current_q:
                           if current_q["analysis"] or line.startswith("答") or "答案" in line[:8]:
                               current_q["analysis"] += "\n" + line
                           else:
                               current_q["title"] += "\n" + line
                      continue
            # -----------------------------

            # 0. Check for Group Header (Shared Options/Stem)
            match_group = re_group_header.match(line)
            if match_group:
                if current_q:
                    current_q['seq'] = current_q.get('seq') or (re.match(r'^(\d+)', current_q['title']).group(1) if re.match(r'^(\d+)', current_q['title']) else None)
                    finalize_question(current_q)
                    current_chapter["questions"].append(current_q)
                    current_q = None
                
                group_info = {
                    'active': True,
                    'start': int(match_group.group(1)),
                    'end': int(match_group.group(2)),
                    'type': 'options' if '备选答案' in match_group.group(3) else 'stem',
                    'data': [],
                    'stem_text': line.split('：')[-1] if '：' in line else ''
                }
                continue


            # 1. 章节
            match_chap = re_chapter.match(line)
            if match_chap:
                title = match_chap.group(1).strip()
                
                # Check for headers to ignore as new chapters
                if re.match(r'^(目录|儿科学|学习指导|第.版|副?主编|编者|学术秘书|[一二三四五六七八九十]+、|【|（)', title):
                    # Check for Teaching Requirements Section start
                    if "教学要求" in title:
                        in_requirements = True
                        if "desc" not in current_chapter: current_chapter["desc"] = ""
                    
                    # Check for Reference Answers (Q2 format)
                    if "参考答案" in title:
                        # CRITICAL FIX: Finalize pending question (e.g. Q6) BEFORE resetting group_info
                        if current_q:
                             # Ensure we use the current group_info before it gets killed
                             current_q['seq'] = current_q.get('seq') or (re.match(r'^(\d+)', current_q['title']).group(1) if re.match(r'^(\d+)', current_q['title']) else None)
                             finalize_question(current_q)
                             current_chapter["questions"].append(current_q)
                             current_q = None
                        
                        in_ref_answers = True
                        in_case_analysis = False
                        in_noun_exp = False
                        in_requirements = False
                        # We don't continue here because we want to reset group_info below
                        
                    if title.startswith('【') or re.match(r'^[一二三四五六七八九十]+、', title):
                        group_info['active'] = False
                        group_info['data'] = []
                        group_info['stem_text'] = ''
                    continue

                # Reset Group Info on REAL Chapter Change
                group_info['active'] = False
                group_info['data'] = []
                group_info['stem_text'] = ''
                
                # Turn off Answer Mode on new chapter
                in_ref_answers = False
                
                # Logic to Merge Subtitle
                if current_chapter and not current_chapter['questions']:
                     if re.match(r'^第[一二三四五六七八九十0-9]+章', current_chapter['title']):
                          if not re.match(r'^第[一二三四五六七八九十0-9]+章', title):
                               current_chapter['title'] += " " + title
                               continue

                # Modes Check
                if "名词解释" in title:
                    in_noun_exp = True
                    in_case_analysis = False
                    in_requirements = False
                elif "病例分析" in title or "问答题" in title:
                    in_case_analysis = True
                    in_noun_exp = False
                    in_requirements = False
                else:
                    in_noun_exp = False
                    in_case_analysis = False
                    in_requirements = False

                # If we have a pending question, finalize it before starting new chapter
                if current_q and current_chapter:
                    current_q['seq'] = current_q.get('seq') or (re.match(r'^(\d+)', current_q['title']).group(1) if re.match(r'^(\d+)', current_q['title']) else None)
                    finalize_question(current_q)
                    current_chapter["questions"].append(current_q)
                    current_q = None
                
                current_chapter = {"title": title, "questions": [], "desc": ""}
                all_chapters.append(current_chapter)
                continue

            # --- Reference Answers Mode ---
            if in_ref_answers:
                 if line.startswith('# '):
                       # If we hit another header that isn't answers
                       pass # Let normal header logic handle it (and unset in_ref_answers)
                 else:
                       # Parse Answer Lines: "1. C 2. D" or "1.C"
                       # Use findall to catch multiple answers per line
                       # Regex: (\d+)[\.．]\s*([A-Za-z]+)
                       ans_matches = re.findall(r'(\d+)[\.．]\s*([A-Za-z]+)', line)
                       if ans_matches:
                           for seq, ans in ans_matches:
                                # Find question in current chapter with this seq
                                found_q = False
                                for q in current_chapter['questions']:
                                     if str(q['seq']) == str(seq): # Ensure string comparison
                                          q['answer'] = ans
                                          if len(ans) > 1: q['type'] = 'multi'
                                          found_q = True
                                          break
                       continue
            # ------------------------------

            # 2. 题目
            match_q = re_question_start.match(line)
            if match_q:
                # New Question Found
                if current_q:
                    current_q['seq'] = current_q.get('seq') or (re.match(r'^(\d+)', current_q['title']).group(1) if re.match(r'^(\d+)', current_q['title']) else None)
                    finalize_question(current_q)
                    current_chapter["questions"].append(current_q)
                
                current_q = {
                    "id": "",
                    "seq": match_q.group(1),
                    "title": match_q.group(2).strip(),
                    "options": [],
                    "answer": "",
                    "analysis": "",
                    "type": "single"
                }
                continue

            # 3. Handle Standalone Answer Line (e.g. Q1 "您的答案...")
            match_full_ans = re_full_ans_line.match(line)
            if current_q and match_full_ans:
                 q_ans = match_full_ans.group(1).strip().replace(' ', '')
                 if q_ans:
                      current_q["answer"] = q_ans
                 continue

            # 4. Handle Inline / Start-of-Line Options
            # Try to extract trailing answer on the same line first
            tail_match = re_ans_tail.search(line)
            content_to_parse = line
            
            if tail_match and not line.startswith("答") and not line.startswith("解析") and current_q:
                  q_ans = tail_match.group(1).strip().replace(' ', '')
                  if q_ans: current_q["answer"] = q_ans
                  content_to_parse = line[:tail_match.start()]

            # Find all options in the line (Handles 'A:...' 'B:...' and 'A. ...')
            inline_opts = re_inline_opt.findall(content_to_parse)
            if inline_opts:
                 for label, text in inline_opts:
                      opt = {"label": label, "text": text.strip()}
                      if current_q:
                           current_q["options"].append(opt)
                      
                      # ALWAYS append to group_info if active (Fix for shared options)
                      if group_info['active'] and group_info['type'] == 'options':
                           group_info['data'].append(opt)
                 continue

            # 5. Analysis/Content Append
            if current_q:
                match_ana = re_analysis.match(line)
                if match_ana:
                    current_q["analysis"] += match_ana.group(1)
                else:
                    if not current_q["options"]: # If no options yet, maybe part of title?
                          # Check if it looks like start of option A?
                          if not re.match(r'^[A-G][:.]', line):
                               current_q["title"] += "\n" + line
                    else:
                          pass # Ignore extra text after options? Or append to last option?
            
            # 6. 特殊处理：单行包含选项、答案的情况 (Inline Options)
            # 例子: A:xxx B:xxx 您的答案是：A 正确答案是：A
            # 或者是 A:xxx B:xxx ...
            
            # 首先尝试分离尾部的答案信息 "您的答案是..."
            re_ans_tail = re.compile(r'\s*(您的答案.*)$')
            tail_match = re_ans_tail.search(line)
            
            line_content = line
            tail_content = ""
            if tail_match:
                tail_content = tail_match.group(1)
                line_content = line[:tail_match.start()]
                
                # 尝试从尾部提取答案
                # tail_str like "您的答案是：A 正确答案是：A"
                # 简单提取 "正确答案是：X"
                real_ans_match = re.search(r'正确答案(?:是)?[:：]\s*([A-Z]+)', tail_content)
                if real_ans_match and current_q:
                    ans_str = real_ans_match.group(1).replace(' ', '')
                    current_q["answer"] = ans_str
                    if len(ans_str) > 1: current_q["type"] = "multi"

            # 提取行内选项
            # 正则: ([A-E])[:\.\、]\s*(.*?)(?=\s*[A-E][:\.\、]|$|您的答案|正确答案)
            re_inline_opt = re.compile(r'([A-E])[:\.\、]\s*(.*?)(?=\s*[A-E][:\.\、]|\s*您的答案|\s*正确答案|$)', re.DOTALL)
            inline_opts = re_inline_opt.findall(line_content)
            
            if inline_opts:
                if current_q:
                    for tag, text in inline_opts:
                         current_q["options"].append({
                            "label": tag,
                            "text": text.strip()
                        })
                continue

            # 7. 特殊处理：单独的 "您的答案...正确答案..." 行
            # 如果不处理，会被当做文本追加到上一行(通常是最后一个选项)
            # 允许 "您的答案" 部分缺失 (即只包含 正确答案)
            # 6. Legacy inline check (Removed)
            match_full_ans = re_full_ans_line.match(line)
            if current_q and match_full_ans:
                real_ans = match_full_ans.group(1).strip()
                if real_ans:
                    current_q["answer"] = real_ans
                    if len(real_ans) > 1: current_q["type"] = "multi"
                continue

            # 8. 内容追加 (如果不是选项也不是答案，就追加到上一级)
            if current_q:
                # 如果刚才分离出的 tail 包含答案，可能还有解析信息? 暂不处理复杂解析
                if current_q["analysis"]:
                    current_q["analysis"] += "\n" + line # Markdown 换行
                elif current_q["options"]:
                    # 之前的逻辑: 如果有选项了，新行追加到最后一个选项
                    # 但如果是 inline options 刚刚加进去的，不要轻易追加下一行，除非下一行确实是文本
                    # 这里保持原有逻辑即可
                    current_q["options"][-1]["text"] += " " + line
                else:
                    current_q["title"] += " " + line

        # 文件结束，保存最后一道题
        if current_q and current_chapter:
            finalize_question(current_q)
            current_chapter["questions"].append(current_q)

    # 过滤空章节
    return [c for c in all_chapters if c["questions"]]

def parse_q2_markdown(file_path):
    print(f"Processing Q2 (Structured) {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    chapters = []
    current_chap = None
    
    # 状态机：'none', 'req' (要求), 'qs' (复习题), 'ans' (答案)
    section_state = 'none' 
    
    # 预编译正则
    re_chap_start = re.compile(r'^#\s+第.+章')
    re_chap_title = re.compile(r'^#\s+(.+)')
    re_section_req = re.compile(r'^#\s+一、教学要求')
    re_section_qs = re.compile(r'^#\s+二、复习题')
    re_section_ans = re.compile(r'^#\s+三、参考答案')
    
    re_q_start = re.compile(r'^(\d+)\s*[\.、]\s*(.*)')
    re_opt = re.compile(r'^\s*([A-E])\s*[\.、]\s*(.*)')
    
    # 答案行匹配: "1.A 2.B" 或 "1. A"
    re_ans_line = re.compile(r'(\d+)\s*[\.、]?\s*([A-E]+)')

    current_q = None

    for line in lines:
        line = line.strip()
        if not line: continue

        # 1. 扫描章节头
        if re_chap_start.match(line):
            # 保存上一题
            if current_q and current_chap:
                full_content = current_q['title'] + "".join([o['text'] for o in current_q['options']])
                current_q['id'] = generate_hash_id(full_content)
                current_chap["questions"].append(current_q)
                current_q = None

            current_chap = {"title": line.replace('#','').strip(), "questions": []}
            chapters.append(current_chap)
            section_state = 'none'
            continue
            
        # 尝试捕捉章节副标题（如果是紧接在章节下面的由#开头的）
        if current_chap and section_state == 'none' and line.startswith('#') and not any(x.match(line) for x in [re_section_req, re_section_qs, re_section_ans]):
             # 可能是标题 "绪论"
             title_part = line.replace('#','').strip()
             if title_part not in ["目录", "儿科学", "学习指导与习题集", "第③版", "儿科学学习指导与习题集"]:
                 current_chap['title'] += " " + title_part
             continue

        # 2. 状态切换
        if re_section_req.match(line):
            section_state = 'req'
            continue
        if re_section_qs.match(line):
            section_state = 'qs'
            continue
        if re_section_ans.match(line):
            # 保存最后一题
            if current_q and current_chap:
                full_content = current_q['title'] + "".join([o['text'] for o in current_q['options']])
                current_q['id'] = generate_hash_id(full_content)
                current_chap["questions"].append(current_q)
                current_q = None
            section_state = 'ans'
            continue
            
        # 3. 根据状态处理内容
        if section_state == 'qs':
            # 忽略题目区的小标题如 【A1型题】
            if line.startswith('#') or line.startswith('【'): 
                continue

            # 题目开始
            match_q = re_q_start.match(line)
            if match_q:
                # 保存上一题
                if current_q and current_chap:
                    full_content = current_q['title'] + "".join([o['text'] for o in current_q['options']])
                    current_q['id'] = generate_hash_id(full_content)
                    current_chap["questions"].append(current_q)
                
                current_q = {
                    "id": "",
                    "seq": int(match_q.group(1)), # 暂存序号用于对答案
                    "title": match_q.group(2),
                    "options": [],
                    "answer": "",
                    "analysis": "", # Q2 似乎没解析，只有答案
                    "type": "single"
                }
                continue

            # 选项
            match_opt = re_opt.match(line)
            if current_q and match_opt:
                current_q["options"].append({
                    "label": match_opt.group(1),
                    "text": match_opt.group(2)
                })
                continue
            
            # 题目内容追加
            if current_q:
                if current_q["options"]:
                    current_q["options"][-1]["text"] += " " + line
                else:
                    current_q["title"] += " " + line

        elif section_state == 'ans':
            if not current_chap: continue
            # 提取答案 "1. A 2. B"
            # 简单分词处理
            # 移除常见干扰神
            clean_line = line.replace('~', ' ').replace('题', '') 
            matches = re_ans_line.findall(clean_line)
            for seq_str, ans_str in matches:
                seq = int(seq_str)
                # 在当前章节查找序号匹配的题目
                # 注意：题目的顺序可能就是列表顺序，但序号可能不连续（如果中间有非题文本）。
                # 为简单起见，且为了高性能，我们假设序号是递增的。但比较稳妥的是遍历查找。
                # 倒序查找比较快？
                 # Find question with seq
                for q in current_chap["questions"]:
                    if q.get('seq') == seq:
                         q['answer'] = ans_str
                         if len(ans_str) > 1: q['type'] = 'multi'
                         break
        
        elif section_state == 'noun':
            # Noun explanation parsing
            # Format:
            # # Term
            # Explanation textual block...
            
            match_term = re_noun_term.match(line)
            if match_term:
                # Save previous term if exists
                if current_q and current_chapter:
                    finalize_question(current_q)
                    current_chapter["questions"].append(current_q)
                
                # New Term Question
                current_q = {
                    "id": "",
                    "title": match_term.group(1).strip() + " (名词解释)",
                    "options": [],
                    "answer": "见解析",
                    "analysis": "",
                    "type": "essay" # Short answer / Essay type
                }
                continue
            
            # Content of the explanation
            if current_q:
                current_q["analysis"] += line + "\n"

    # End of file
    if current_q and current_chapter:
        finalize_question(current_q)
        current_chapter["questions"].append(current_q)

    return chapters

def get_html_template(json_data):
    # Process LaTeX backslashes for Marked.js compat
    # We must double-escape backslashes inside $...$ so they survive into MathJax
    def fix_tex(text):
        r"""
        Robustly handle MathJax:
        1. Split by '$' to separate Text vs Math.
        2. In Text chunks: Find unwrapped LaTeX (e.g. \mathrm{cm}, 10^9) and wrap them.
        3. In Math chunks: Double-escape backslashes for Marked.js.
        4. Rejoin.
        """
        if not text: return text
        
        # Split by $ (but keep the delimiters implicitly by logic)
        parts = text.split('$')
        
        new_parts = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # Inside $...$ (Math chunk)
                # Double escape backslashes: \ -> \\
                part = part.replace('\\', '\\\\')
                part = part.replace('~', ' ') # Tilde to space often helps spacing in MathJax
                new_parts.append(part)
            else:
                # Outside $...$ (Text chunk)
                # We need to find stray LaTeX and wrap it.
                
                # 1. Fix Roman Numerals like III^{\circ} or \mathrm{III}^{\circ}
                # Pattern: Optional \mathrm{...} around Roman Numeral, followed by ^...
                # We simply look for the sequence and wrap it all.
                # Regex: (?:\\mathrm\{)? ...
                # Actually, let's just catch Roman+Superscript first.
                part = re.sub(r'(?<!\$)\b([IVX]+(?:[\^_](?:\{[^}]+\}|\\circ|\d+)))\b', r'$\1$', part)

                # 2. Wrap \mathrm{...}, potentially followed by superscript/subscript (e.g. \mathrm{g}^{\circ})
                # We need to capture the following ^... if present to keep it inside $.
                # Matches: \mathrm{...} followed optionally by ^... or _...
                # Note: This primitive regex assumes no nested braces in the ^ part unless simply {...}
                def repl_mathrm(m):
                    base = m.group(1) # \mathrm{...}
                    sups = m.group(2) or "" # ^...
                    return f'${base}{sups}$'
                
                part = re.sub(r'(?<!\$)(\\mathrm\{[^}]+\})(?:([\^_](?:\{[^}]+\}|\\circ|\d+|[a-zA-Z])))?', repl_mathrm, part)

                # 3. Wrap Dimensions: 1.5 \times 2.0
                part = re.sub(r'(?<!\$)(\d+(?:\.\d+)?)\s*\\times\s*(\d+(?:\.\d+)?)', r'$\1 \\times \2$', part)

                # 4. Wrap common standalone math symbols
                # \sim, \approx, \le, \ge, \pm, \rightarrow, \times (if not caught above)
                part = re.sub(r'(?<!\$)\\((?:sim|approx|le|ge|pm|rightarrow|times)(?![a-zA-Z]))', r'$\\\1$', part)

                # 5. Fix exponents: 10^9 or 10^{-9}
                part = re.sub(r'(?<!\$)\b10\^\{?(-?\d+)\}?', r'$10^{\1}$', part)
                
                # 6. Fix temperature: 39.5^\circ C or 39.5^{\circ}C
                # Often appears as: 39 ^\circ C or similar
                part = re.sub(r'(?<!\$)(\d+(?:\.\d+)?)\s*[\^_]\{?\\circ\}\s*C', r'$\1^{\\circ}C$', part)
                
                new_parts.append(part)
        
        # Rejoin with $ delimiters
        # Note: split gives n parts. Join with '$' restores the delimiters.
        # But wait: "text $math$ text". split -> ["text ", "math", " text"]
        # join('$') -> "text $math$ text". Correct.
        return '$'.join(new_parts)

    for book in json_data:
        for chap in book.get('chapters', []):
            for q in chap.get('questions', []):
                q['title'] = fix_tex(q.get('title', ''))
                q['analysis'] = fix_tex(q.get('analysis', ''))
                q['answer'] = fix_tex(q.get('answer', '')) # Answer might have latex too
                if 'options' in q:
                    for opt in q['options']:
                        opt['text'] = fix_tex(opt['text'])

    data_js = json.dumps(json_data, ensure_ascii=False)
    
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>儿科题库 (Pediatrics QBank)</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script>
    MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']]
      }},
      svg: {{
        fontCache: 'global'
      }}
    }};
    </script>
    <script type="text/javascript" id="MathJax-script" async
      src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js">
    </script>
    <style>
        :root {{
            --bg: #f4f6f9; --text: #333; --card: #fff;
            --primary: #4a90e2; --success: #2ecc71; --danger: #e74c3c;
            --border: #e1e4e8; --gray: #888;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #1a1a1a; --text: #e0e0e0; --card: #2d2d2d;
                --primary: #5d9cec; --border: #444;
            }}
            .option.correct {{ background: rgba(46, 204, 113, 0.2) !important; border-color: #2ecc71 !important; color: #a2f2c2 !important; }}
            .option.wrong {{ background: rgba(231, 76, 60, 0.2) !important; border-color: #e74c3c !important; color: #f5b7b1 !important; }}
        }}
        body {{ font-family: -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; height: 100vh; display: flex; overflow: hidden; }}
        
        /* 布局 */
        .sidebar {{ width: 280px; background: var(--card); border-right: 1px solid var(--border); overflow-y: auto; flex-shrink: 0; display: flex; flex-direction: column; }}
        .book-switcher {{ display: flex; border-bottom: 1px solid var(--border); background: var(--bg); }}
        .book-tab {{ flex: 1; padding: 12px; text-align: center; cursor: pointer; font-size: 14px; font-weight: 500; color: var(--gray); border-bottom: 2px solid transparent; }}
        .book-tab.active {{ color: var(--primary); border-bottom-color: var(--primary); background: var(--card); }}
        
        .main {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; }}
        .chapter-list {{ flex: 1; overflow-y: auto; }}
        .chapter-item {{ padding: 12px 15px; border-bottom: 1px solid var(--border); cursor: pointer; font-size: 14px; }}
        .chapter-item:hover {{ background: var(--bg); }}
        .chapter-item.active {{ background: rgba(74, 144, 226, 0.1); color: var(--primary); border-left: 4px solid var(--primary); }}
        
        .toolbar {{ padding: 10px; background: var(--card); border-bottom: 1px solid var(--border); display: flex; gap: 10px; align-items: center; }}
        .search-input {{ flex: 1; padding: 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--text); }}
        
        .content {{ flex: 1; overflow-y: auto; padding: 15px; scroll-behavior: smooth; }}
        .card {{ background: var(--card); border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
        
        /* 题目样式 */
        .q-title {{ font-size: 1.1em; font-weight: 600; margin-bottom: 15px; line-height: 1.5; }}
        .option {{ padding: 10px; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; cursor: pointer; display: flex; }}
        .option:hover {{ background: rgba(0,0,0,0.02); }}
        .option.selected {{ border-color: var(--primary); background: rgba(74, 144, 226, 0.05); }}
        .option.correct {{ background: rgba(46, 204, 113, 0.15); border-color: var(--success); color: #155724; }}
        .option.wrong {{ background: rgba(231, 76, 60, 0.15); border-color: var(--danger); color: #721c24; }}
        
        /* 解析与数据 */
        .group-options-box {{ background: var(--bg); padding: 10px; border-radius: 6px; margin-bottom: 10px; border: 1px dashed var(--gray); font-size: 0.9em; }}
        .group-option-item {{ margin-bottom: 4px; }}
        .simple-options-container {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 5px; }}
        .simple-option-btn {{ width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border); border-radius: 50%; cursor: pointer; font-weight: bold; background: var(--card); }}
        .simple-option-btn:hover {{ background: rgba(0,0,0,0.05); }}
        .simple-option-btn.selected {{ border-color: var(--primary); background: var(--primary); color: white; }}
        .simple-option-btn.correct {{ border-color: var(--success); background: var(--success); color: white; }}
        .simple-option-btn.wrong {{ border-color: var(--danger); background: var(--danger); color: white; }}

        .analysis-box {{ margin-top: 15px; padding: 15px; background: var(--bg); border-radius: 6px; display: none; }}
        .analysis-box.show {{ display: block; }}
        .stat-btn {{ color: var(--primary); cursor: pointer; text-decoration: underline; font-size: 0.9em; margin-left: 10px; }}
        .stat-display {{ display: none; font-weight: bold; color: var(--primary); margin-left: 5px; }}
        
        /* 底部操作 */
        .footer-actions {{ margin-top: 15px; padding-top: 10px; border-top: 1px solid var(--border); display: flex; gap: 20px; color: var(--gray); font-size: 0.9em; }}
        .action {{ cursor: pointer; display: flex; align-items: center; gap: 4px; }}
        .action:hover {{ color: var(--primary); }}
        .fav-active {{ color: #f1c40f; }}

        /* 评论区 */
        .comments-box {{ margin-top: 15px; display: none; border-top: 1px dashed var(--border); padding-top: 10px; }}
        .comment-item {{ font-size: 0.9em; padding: 8px 0; border-bottom: 1px solid var(--border); }}
        .comment-item p {{ margin: 4px 0 0 0; }}
        .md-content img {{ max-width: 100%; }} /* Markdown 图片适配 */
        
        /* 移动端 */
        @media (max-width: 768px) {{
            .sidebar {{ position: absolute; height: 100%; z-index: 100; transform: translateX(-100%); transition: 0.3s; }}
            .sidebar.show {{ transform: translateX(0); }}
            .toggle-menu {{ display: block; }}
        }}

        /* 模态框 */
        .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; justify-content: center; align-items: center; }}
        .modal.show {{ display: flex; }}
        .modal-content {{ background: var(--card); padding: 25px; border-radius: 8px; width: 300px; max-width: 90%; position: relative; }}
        .close-btn {{ position: absolute; top: 10px; right: 10px; cursor: pointer; font-size: 20px; }}
        .form-group {{ margin-bottom: 15px; }}
        .form-group label {{ display: block; margin-bottom: 5px; font-size: 0.9em; }}
        .form-input {{ width: 100%; padding: 8px; border: 1px solid var(--border); border-radius: 4px; box-sizing: border-box; }}
        .btn-primary {{ width: 100%; padding: 10px; background: var(--primary); color: white; border: none; border-radius: 4px; cursor: pointer; }}
        .btn-secondary {{ width: 100%; padding: 10px; background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 4px; cursor: pointer; margin-top: 10px; }}
        .user-info {{ display: flex; align-items: center; gap: 10px; margin-right: 15px; font-size: 14px; cursor: pointer; }}
    </style>
</head>
<body>

<div class="sidebar" id="sidebar">
    <div class="book-switcher" id="bookTabs"></div>
    <div class="chapter-list" id="chapList"></div>
</div>

<div class="main">
    <div class="toolbar">
        <button onclick="toggleSidebar()" style="background:none; border:1px solid var(--border); padding:5px 10px; border-radius:4px; color:var(--text)">☰</button>
        <input class="search-input" id="search" placeholder="搜索题目..." oninput="filterQ()">
        <button onclick="toggleWrong()" id="btnWrong" style="background:none; border:1px solid var(--border); padding:5px; border-radius:4px; color:var(--text)">只看错题</button>
        <button onclick="resetProgress()" style="background:none; border:1px solid var(--border); padding:5px; border-radius:4px; color:var(--text); margin-left:5px" title="重置本章进度">↺</button>
        <div style="flex:1"></div> 
        <div id="user-area" class="user-info" onclick="showUserModal()">
            <span id="user-name">未登录</span> 👤
        </div>
    </div>
    <div class="content" id="content"></div>
</div>

<div id="auth-modal" class="modal">
    <div class="modal-content">
        <span class="close-btn" onclick="closeModal()">×</span>
        
        <div id="auth-form">
            <h3 id="auth-title">登录</h3>
            <div class="form-group">
                <label>用户名</label>
                <input type="text" id="u-name" class="form-input">
            </div>
            <div class="form-group">
                <label>密码</label>
                <input type="password" id="u-pass" class="form-input">
            </div>
            <div class="form-group" id="invite-group" style="display:none">
                <label>邀请码 (注册必填)</label>
                <input type="text" id="u-code" class="form-input">
            </div>
            <button class="btn-primary" onclick="doAuth()">提交</button>
            <div style="margin-top:10px; text-align:center; font-size:12px">
                <a href="#" onclick="toggleAuthMode()">没有账号？去注册</a>
            </div>
        </div>

        <div id="user-panel" style="display:none">
            <h3>个人中心</h3>
            <p>你好, <b id="panel-name"></b></p>
            <p style="font-size:12px; color:var(--gray)">云端最后同步: <span id="sync-time">从未</span></p>
            
            <button class="btn-primary" onclick="syncUpload()">☁️ 备份进度到云端</button>
            <button class="btn-secondary" onclick="syncDownload()">⬇️ 从云端恢复进度</button>
            <button class="btn-secondary" onclick="logout()" style="border-color:var(--danger); color:var(--danger)">退出登录</button>
        </div>
    </div>
</div>

<script>
    const BOOKS = {data_js}; // [ {{id, title, chapters: []}} ]
    const API = "{DOMAIN}/api";
    
    let state = {{
        bookIdx: 0,
        chapIdx: 0,
        onlyWrong: false,
        records: JSON.parse(localStorage.getItem('qb_records') || '{{}}'), 
        favs: JSON.parse(localStorage.getItem('qb_favs') || '[]'),
        stats: {{}}, 
        nick: localStorage.getItem('qb_nick') || '',
        user: JSON.parse(localStorage.getItem('qb_user') || 'null')
    }};

    // ================= 用户系统 =================
    let isRegister = false;

    function updateUserUI() {{
        const area = document.getElementById('user-name');
        if (state.user) {{
            area.innerText = state.user.username;
            area.style.color = 'var(--primary)';
        }} else {{
            area.innerText = '登录/注册';
            area.style.color = 'var(--text)';
        }}
    }}

    function showUserModal() {{
        document.getElementById('auth-modal').classList.add('show');
        if (state.user) {{
            document.getElementById('auth-form').style.display = 'none';
            document.getElementById('user-panel').style.display = 'block';
            document.getElementById('panel-name').innerText = state.user.username;
        }} else {{
            document.getElementById('auth-form').style.display = 'block';
            document.getElementById('user-panel').style.display = 'none';
        }}
    }}

    function closeModal() {{
        document.getElementById('auth-modal').classList.remove('show');
    }}

    function toggleAuthMode() {{
        isRegister = !isRegister;
        document.getElementById('auth-title').innerText = isRegister ? '注册新账号' : '登录';
        const link = document.querySelector('#auth-form a');
        link.innerText = isRegister ? '已有账号？去登录' : '没有账号？去注册';
        // Show/Hide Invite Code
        document.getElementById('invite-group').style.display = isRegister ? 'block' : 'none';
    }}

    async function doAuth() {{
        const name = document.getElementById('u-name').value;
        const pass = document.getElementById('u-pass').value;
        const code = document.getElementById('u-code').value; // Get Invite Code
        
        if (!name || !pass) return alert('请输入完整');
        if (isRegister && !code) return alert('请输入邀请码');

        const action = isRegister ? 'register' : 'login';
        const btn = document.querySelector('#auth-form button');
        btn.innerText = '处理中...'; btn.disabled = true;

        try {{
            const payload = {{ username: name, password: pass }};
            if (isRegister) payload.inviteCode = code; // Send Invite Code

            const res = await fetch(`${{API}}/user?action=${{action}}`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload)
            }});
            const data = await res.json();
            
            if (data.error) throw new Error(data.error);
            
            if (isRegister) {{
                alert('注册成功，请登录');
                toggleAuthMode();
            }} else {{
                state.user = {{ username: data.username, token: data.token }};
                localStorage.setItem('qb_user', JSON.stringify(state.user));
                updateUserUI();
                closeModal();
                // 登录后尝试自动拉取一次时间检查（可选）
                alert('登录成功！请记得定期备份数据。');
            }}
        }} catch (e) {{
            alert(e.message);
        }} finally {{
            btn.innerText = '提交'; btn.disabled = false;
        }}
    }}

    function logout() {{
        state.user = null;
        localStorage.removeItem('qb_user');
        updateUserUI();
        closeModal();
    }}

    // ================= 数据同步 =================
    
    async function syncUpload() {{
        if (!state.user) return alert('请先登录');
        if (!confirm('确定要将本地进度上传覆盖云端吗？')) return;

        try {{
            const res = await fetch(`${{API}}/user?action=upload`, {{
                method: 'POST',
                headers: {{ 
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + state.user.token 
                }},
                body: JSON.stringify({{ records: state.records, favs: state.favs }})
            }});
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            
            alert('备份成功！');
            document.getElementById('sync-time').innerText = new Date().toLocaleString();
        }} catch (e) {{
            alert('上传失败: ' + e.message);
            if (e.message.includes('失效')) logout();
        }}
    }}

    async function syncDownload() {{
        if (!state.user) return alert('请先登录');
        if (!confirm('警告：这将使用云端数据覆盖本地进度，本地未备份的数据将丢失！确定吗？')) return;

        try {{
            const res = await fetch(`${{API}}/user?action=download`, {{
                method: 'GET',
                headers: {{ 'Authorization': 'Bearer ' + state.user.token }}
            }});
            const data = await res.json();
            if (data.error) throw new Error(data.error);
            if (data.empty) return alert('云端暂无备份数据');

            // 恢复数据
            state.records = data.records || {{}};
            state.favs = data.favs || [];
            
            // 写入本地存储
            localStorage.setItem('qb_records', JSON.stringify(state.records));
            localStorage.setItem('qb_favs', JSON.stringify(state.favs));
            
            // 刷新界面
            alert('恢复成功！');
            document.getElementById('sync-time').innerText = new Date(data.updated_at).toLocaleString();
            loadChap(state.chapIdx); // 刷新当前视图
        }} catch (e) {{
            alert('下载失败: ' + e.message);
        }}
    }}

    window.copyQ = (qid) => {{
        const b = BOOKS[state.bookIdx];
        let q = null;
        for(let c of b.chapters) {{
             q = c.questions.find(x=>x.id===qid);
             if(q) break;
        }}
        if(!q) return;
        
        const typeStr = q.type==='multi' ? '多选题' : '单选题';
        let text = `[${{typeStr}}] ${{q.title}}\n`;
        q.options.forEach(o => {{
            text += `${{o.label}}. ${{o.text}}\n`;
        }});
        text += `\n正确答案: ${{q.answer}}`;
        if(q.analysis) text += `\n解析: ${{q.analysis}}`;
        
        navigator.clipboard.writeText(text).then(() => {{
            const btn = document.querySelector(`#card-${{qid}} .action:nth-child(3)`);
            if(btn) {{
                 const origin = btn.innerHTML;
                 btn.innerHTML = '✅ 已复制';
                 setTimeout(()=>btn.innerHTML = origin, 2000);
            }}
        }}).catch(err=>alert('复制失败'));
    }};

    window.filterQ = () => {{
        renderList();
    }};

    window.toggleAnalysis = (qid) => {{
        const box = document.getElementById(`analysis-${{qid}}`);
        if(box) box.classList.toggle('show');
    }};

    function init() {{
        renderBooks();
        loadChap(0);
        updateUserUI();
        window.onbeforeunload = () => {{
            localStorage.setItem('qb_records', JSON.stringify(state.records));
            localStorage.setItem('qb_favs', JSON.stringify(state.favs));
        }};
    }}

    function renderBooks() {{
        const html = BOOKS.map((b, i) => 
            `<div class="book-tab ${{i===state.bookIdx?'active':''}}" onclick="switchBook(${{i}})">${{b.title}}</div>`
        ).join('');
        document.getElementById('bookTabs').innerHTML = html;
    }}
    
    function switchBook(idx) {{
        state.bookIdx = idx;
        renderBooks(); // update active tab
        loadChap(0);
    }}

    function renderMenu() {{
        const chapters = BOOKS[state.bookIdx].chapters;
        document.getElementById('chapList').innerHTML = chapters.map((c, i) => 
            `<div class="chapter-item ${{i===state.chapIdx?'active':''}}" onclick="loadChap(${{i}})">
                ${{c.title}} <span style="font-size:0.8em; color:var(--gray)">(${{c.questions.length}})</span>
            </div>`
        ).join('');
    }}

    function loadChap(idx) {{
        state.chapIdx = idx;
        renderMenu();
        document.getElementById('sidebar').classList.remove('show');
        renderList();
        
        // 批量获取统计数据
        const data = BOOKS[state.bookIdx];
        if(!data.chapters[idx]) return;
        
        const ids = data.chapters[idx].questions.map(q => q.id);
        fetch(API + '/batch-info', {{
            method: 'POST', body: JSON.stringify({{ ids }})
        }}).then(r=>r.json()).then(res => {{
            state.stats = {{ ...state.stats, ...res }};
            updateStatsUI(ids); 
        }});
    }}

    function renderList() {{
        const b = BOOKS[state.bookIdx];
        if (!b || !b.chapters[state.chapIdx]) return;
        
        const qs = b.chapters[state.chapIdx].questions;
        const kw = document.getElementById('search').value.toLowerCase();
        
        // Calculate Stats for Chart
        let done = 0, correct = 0, wrong = 0;
        qs.forEach(q => {{
            const rec = state.records[q.id];
            if (rec && rec.status) {{
                done++;
                if (rec.status === 'correct') correct++;
                else wrong++;
            }}
        }});
        const total = qs.length;
        const pCorrect = total ? (correct / total * 100) : 0;
        const pWrong = total ? (wrong / total * 100) : 0;
        // const pUndone = total ? 100 - pCorrect - pWrong : 100; // Not directly used in conic-gradient, calculated implicitly

        // Sticky Header HTML
        const chartHtml = `
        <div id="chap-header" style="position:sticky; top:0; z-index:100; background:rgba(255,255,255,0.95); backdrop-filter:blur(5px); padding:10px 15px; border-bottom:1px solid #eee; display:flex; align-items:center; justify-content:space-between; margin: -15px -15px 15px -15px; box-shadow:0 2px 5px rgba(0,0,0,0.05)">
            <div style="font-weight:bold; font-size:1.1em">${{b.chapters[state.chapIdx].title}}</div>
            <div style="display:flex; align-items:center; gap:10px">
                <div class="text-stats" style="text-align:right; font-size:12px; line-height:1.2; color:#666">
                    <div>已做 ${{done}}/${{total}}</div>
                    <div>正确率 ${{done ? Math.round(correct/done*100) : 0}}%</div>
                </div>
                <!-- Pie Chart with CSS Conic Gradient -->
                <div class="chart-container" style="width:36px; height:36px; border-radius:50%; background: conic-gradient(
                    var(--success) 0% ${{pCorrect}}%, 
                    var(--danger) ${{pCorrect}}% ${{pCorrect + pWrong}}%, 
                    #eee ${{pCorrect + pWrong}}% 100%
                )"></div>
            </div>
        </div>`;

        // Description HTML (Teaching Objectives)
        const chapDesc = b.chapters[state.chapIdx].desc;
        const descHtml = chapDesc ? `<div class="chapter-desc" style="background:#f9f9f9; padding:15px; border-radius:8px; margin-bottom:20px; border-left:4px solid var(--primary); color:#555; font-size:0.95em; line-height:1.6">${{chapDesc}}</div>` : '';

        const listHtml = qs.filter(q => {{
            const isWrong = state.records[q.id]?.status === 'wrong';
            if (state.onlyWrong && !isWrong) return false;
            return q.title.toLowerCase().includes(kw) || q.id.includes(kw);
        }}).map((q, i, arr) => {{
             // Check if group start
             const prev = arr[i-1];
             const isGroupStart = q.group_id && (!prev || prev.group_id !== q.group_id);
             return buildCard(q, isGroupStart);
        }}).join('');
        
        document.getElementById('content').innerHTML = chartHtml + descHtml + (listHtml || '<div style="text-align:center; padding:20px; color:var(--gray)">没有找到题目</div>');
        
        // 恢复状态
        qs.forEach(q => {{
            if (state.records[q.id]?.checked) checkAnswer(q.id, true);
        }});

        // 渲染数学公式
        if (window.MathJax) {{
             MathJax.typesetPromise && MathJax.typesetPromise();
        }}
    }}

    function buildCard(q, isGroupStart = false) {{
        const isFav = state.favs.includes(q.id);
        const stat = state.stats[q.id] || {{ fav:0, rate:0, total:0 }};
        
        // Group Header (Shared Options)
        let groupHeader = '';
        if (isGroupStart && q.group_id) {{
             const optsHtml = q.options.map(o => 
                 `<div class="group-option-item"><b>${{o.label}}.</b> ${{o.text}}</div>`
             ).join('');
             groupHeader = `<div class="group-options-box">${{optsHtml}}</div>`;
        }}

        let contentHtml = '';
        let optionsHtml = '';

        if (q.type === 'essay' || q.type === 'mix' || q.type === 'case') {{
             optionsHtml = `<button onclick="toggleAnalysis('${{q.id}}')" style="padding:8px 15px; background:var(--primary); color:#fff; border:none; border-radius:4px; cursor:pointer">查看答案</button>`;
        }} else {{
             // If grouped, show simplified buttons
             if (q.group_id) {{
                  optionsHtml = `<div class="simple-options-container">` + 
                      q.options.map(o => 
                        `<div class="simple-option-btn" id="opt-${{q.id}}-${{o.label}}" onclick="clickOpt('${{q.id}}', '${{o.label}}', '${{q.type}}')">${{o.label}}</div>`
                      ).join('') + 
                  `</div>`;
             }} else {{
                  // Normal Display
                  optionsHtml = q.options.map(o => 
                    `<div class="option" id="opt-${{q.id}}-${{o.label}}" onclick="clickOpt('${{q.id}}', '${{o.label}}', '${{q.type}}')">
                        <b style="width:25px">${{o.label}}.</b> 
                        <span>${{o.text}}</span>
                     </div>`
                ).join('');
             }}
        }}

        const submitBtn = q.type === 'multi' ? `<button onclick="checkAnswer('${{q.id}}')" style="margin-top:10px; padding:5px 15px; background:var(--primary); color:#fff; border:none; border-radius:4px">提交</button>` : '';

        // Label for question type
        let typeLabel = '单选题';
        if (q.type === 'multi') typeLabel = '多选题';
        else if (q.type === 'essay') typeLabel = '名词解释';
        else if (q.type === 'mix') typeLabel = '简答题';
        else if (q.type === 'case') typeLabel = '病例分析';

        const seqBadge = q.seq ? `<span class="badg">[${{q.seq}}]</span>` : '';

        return `
        <div class="card" id="card-${{q.id}}">
            <div style="font-size:12px; color:var(--gray); margin-bottom:5px">ID: ${{q.id}} · ${{typeLabel}}</div>
            ${{groupHeader}}
            <div class="q-title">
                ${{seqBadge}} 
                ${{marked.parse(q.title)}}
            </div>
            <div>${{optionsHtml}}</div>
            ${{submitBtn}}
            
            <div class="analysis-box" id="analysis-${{q.id}}">
                <div><strong>参考答案:</strong> ${{q.answer || '见解析'}}</div>
                <div style="margin-top:5px"><strong>解析:</strong> 
                    <div class="md-content">${{marked.parse(q.analysis || '暂无解析')}}</div>
                    ${{ (q.type === 'essay' || q.type === 'mix' || q.type === 'case') ? '' : 
                    `<span class="stat-btn" onclick="showRate('${{q.id}}', this)">📊 查看正确率</span>
                    <span class="stat-display" id="rate-${{q.id}}"></span>` }}
                </div>
            </div>

            <div class="footer-actions">
                <div class="action ${{isFav?'fav-active':''}}" onclick="toggleFav('${{q.id}}', this)">
                    ★ <span class="fav-cnt">${{stat.fav}}</span>
                </div>
                <div class="action" onclick="toggleComments('${{q.id}}')">💬 评论</div>
                <div class="action" onclick="copyQ('${{q.id}}')">📋 复制</div>
            </div>
            
            <div class="comments-box" id="cmt-box-${{q.id}}">
                <div id="cmt-list-${{q.id}}" style="margin-bottom:10px; max-height:200px; overflow-y:auto">加载中...</div>
                <div style="display:flex; gap:5px">
                    <input id="nick-${{q.id}}" placeholder="昵称" style="width:60px; padding:5px" value="${{state.nick}}">
                    <textarea id="cmt-in-${{q.id}}" placeholder="支持 Markdown 格式..." style="flex:1; padding:5px; height:30px"></textarea>
                    <button onclick="postCmt('${{q.id}}')" style="padding:0 10px">发布</button>
                </div>
            </div>
        </div>`;
    }}

    // 交互逻辑
    window.clickOpt = (qid, label, type) => {{
        if (state.records[qid]?.checked) return;
        
        let ans = state.records[qid]?.ans || [];
        if (type === 'single') {{
            state.records[qid] = {{ ans: [label], checked: false }};
            checkAnswer(qid);
        }} else {{
            // 多选切换
            if (ans.includes(label)) ans = ans.filter(x=>x!==label);
            else ans.push(label);
            state.records[qid] = {{ ans, checked: false }};
            // 渲染选中态
            document.querySelectorAll(`#card-${{qid}} .option, #card-${{qid}} .simple-option-btn`).forEach(el => {{
                el.classList.remove('selected');
                const l = el.id.split('-').pop();
                if (ans.includes(l)) el.classList.add('selected');
            }});
        }}
    }};

    window.checkAnswer = (qid, isReplay=false) => {{
        const b = BOOKS[state.bookIdx];
        let q = null;
        for(let c of b.chapters) {{
             q = c.questions.find(x=>x.id===qid);
             if(q) break;
        }}
        if (!q) return; // Fallback scan
        
        const myAns = state.records[qid]?.ans || [];
        
        // 判分
        const rightStr = q.answer.split('').sort().join('');
        const myStr = [...myAns].sort().join('');
        const isCorrect = rightStr === myStr;

        state.records[qid].checked = true;
        state.records[qid].status = isCorrect ? 'correct' : 'wrong';

        // 样式更新
        const card = document.getElementById(`card-${{qid}}`);
        if(card) {{
            card.querySelectorAll('.option, .simple-option-btn').forEach(el => {{
                el.classList.remove('selected');
                // Remove old status classes just in case
                el.classList.remove('correct');
                el.classList.remove('wrong');
                const l = el.id.split('-').pop();
                if (q.answer.includes(l)) el.classList.add('correct');
                else if (myAns.includes(l)) el.classList.add('wrong');
            }});
        }}

        // 显示解析
        const anaBox = document.getElementById(`analysis-${{qid}}`);
        if(anaBox) anaBox.classList.add('show');
        
        // 自动展开评论 (仅在用户刚答完时，回放时不自动展开以免干扰)
        if (!isReplay) {{
             toggleComments(qid, true); 
             // 上报答题结果
             reportAnswer(qid, isCorrect);
             // Update Chart Dynamically
             updateChart();
        }}
    }};

    function reportAnswer(qid, isCorrect) {{
        fetch(API + '/stats', {{
            method: 'POST',
            body: JSON.stringify({{ questionId: qid, type: 'answer', value: isCorrect ? 1 : 0 }})
        }});
    }}
    
    function updateChart() {{
        const b = BOOKS[state.bookIdx];
        if (!b || !b.chapters[state.chapIdx]) return;
        const qs = b.chapters[state.chapIdx].questions;
        
        let done = 0, correct = 0, wrong = 0;
        qs.forEach(q => {{
            const rec = state.records[q.id];
            if (rec && rec.status) {{
                done++;
                if (rec.status === 'correct') correct++;
                else wrong++;
            }}
        }});
        const total = qs.length;
        const pCorrect = total ? (correct / total * 100) : 0;
        const pWrong = total ? (wrong / total * 100) : 0;
        
        const header = document.getElementById('chap-header');
        if(header) {{
            const chartDiv = header.querySelector('.chart-container');
            const textDiv = header.querySelector('.text-stats');
            
            if(textDiv) {{
                textDiv.innerHTML = `<div>已做 ${{done}}/${{total}}</div><div>正确率 ${{done ? Math.round(correct/done*100) : 0}}%</div>`;
            }}
            if(chartDiv) {{
                chartDiv.style.background = `conic-gradient(
                    var(--success) 0% ${{pCorrect}}%, 
                    var(--danger) ${{pCorrect}}% ${{pCorrect + pWrong}}%, 
                    #eee ${{pCorrect + pWrong}}% 100%
                )`;
            }}
        }}
    }}

    window.showRate = (qid, btn) => {{
        const stat = state.stats[qid];
        const span = document.getElementById(`rate-${{qid}}`);
        if (stat && stat.total > 0) {{
            span.innerText = `正确率: ${{stat.rate}}% (共 ${{stat.total}} 次)`;
        }} else {{
            span.innerText = "暂无数据";
        }}
        span.style.display = 'inline';
        btn.style.display = 'none';
    }};

    window.toggleComments = async (qid, forceOpen=false) => {{
        const box = document.getElementById(`cmt-box-${{qid}}`);
        if (!forceOpen && box.style.display === 'block') {{
            box.style.display = 'none';
            return;
        }}
        box.style.display = 'block';
        
        // 加载评论
        const res = await fetch(`${{API}}/comments?qid=${{qid}}`);
        const list = await res.json();
        const html = list.map(c => `
            <div class="comment-item">
                <div><b style="color:var(--primary)">${{c.nickname}}</b> <span style="font-size:0.8em; color:#aaa">${{new Date(c.created_at*1000).toLocaleDateString()}}</span></div>
                <div class="md-content">${{marked.parse(c.content)}}</div>
            </div>`
        ).join('') || '<div style="padding:10px; text-align:center">暂无评论</div>';
        document.getElementById(`cmt-list-${{qid}}`).innerHTML = html;
        if (window.MathJax) MathJax.typesetPromise();
    }};

    window.postCmt = async (qid) => {{
        const nick = document.getElementById(`nick-${{qid}}`).value;
        const content = document.getElementById(`cmt-in-${{qid}}`).value;
        if(!nick || !content) return alert("请填写完整");
        
        localStorage.setItem('qb_nick', nick);
        state.nick = nick;
        
        await fetch(`${{API}}/comments`, {{
            method: 'POST', body: JSON.stringify({{ nickname:nick, content, questionId:qid }})
        }});
        document.getElementById(`cmt-in-${{qid}}`).value = '';
        toggleComments(qid, true);
    }};

    window.toggleFav = async (qid, el) => {{
        const isAdd = !state.favs.includes(qid);
        if(isAdd) state.favs.push(qid);
        else state.favs = state.favs.filter(x=>x!==qid);
        
        // 乐观更新
        el.classList.toggle('fav-active');
        const numSpan = el.querySelector('.fav-cnt');
        numSpan.innerText = parseInt(numSpan.innerText) + (isAdd?1:-1);
        
        fetch(API + '/stats', {{
            method: 'POST', body: JSON.stringify({{ questionId:qid, type:'fav', value: isAdd?1:-1 }})
        }});
    }};

    window.toggleSidebar = () => document.getElementById('sidebar').classList.toggle('show');
    window.toggleWrong = () => {{
        state.onlyWrong = !state.onlyWrong;
        document.getElementById('btnWrong').style.background = state.onlyWrong ? 'var(--primary)' : 'none';
        document.getElementById('btnWrong').style.color = state.onlyWrong ? '#fff' : 'var(--text)';
        renderList();
    }};

    window.resetProgress = () => {{
        if(!confirm("确定要重置当前章节的答题进度吗？此操作不可恢复。")) return;
        const b = BOOKS[state.bookIdx];
        if (!b) return;
        const chap = b.chapters[state.chapIdx];
        if (!chap) return;
        
        let count = 0;
        chap.questions.forEach(q => {{
            if(state.records[q.id]) {{
                delete state.records[q.id];
                count++;
            }}
        }});
        
        if(count > 0) {{
            localStorage.setItem('qb_rec', JSON.stringify(state.records));
            renderList();
            alert(`已重置 ${{count}} 道题目的进度。`);
        }} else {{
            alert("当前章节没有答题记录。");
        }}
    }};
    window.updateStatsUI = (ids) => {{
        ids.forEach(id => {{
            const el = document.querySelector(`#card-${{id}} .fav-cnt`);
            if(el && state.stats[id]) el.innerText = state.stats[id].fav;
        }});
    }};
    
    init();
</script>
</body>
</html>
"""

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    print("Parsing books...")
    
    # Build books data
    books = [
        {
            "id": "q1",
            "title": "儿科学（题库1）",
            "chapters": convert_to_json(['Q1.md'])
        },
        {
            "id": "q2",
            "title": "儿科学习题集（题库2）",
            "chapters": convert_to_json(['Q2.md'])
        }
    ]
    
    print(f"Book 1 chapters: {len(books[0]['chapters'])}")
    print(f"Book 2 chapters: {len(books[1]['chapters'])}")

    html = get_html_template(books)
    
    with open(os.path.join(OUTPUT_DIR, OUTPUT_HTML), 'w', encoding='utf-8') as f:
        f.write(html)
        
    with open(os.path.join(OUTPUT_DIR, '_headers'), 'w', encoding='utf-8') as f:
        f.write("/*\n  Cache-Control: no-cache\n  Access-Control-Allow-Origin: *")

    print("Done! Upload 'dist' and 'functions' to Cloudflare.")

if __name__ == "__main__":
    main()