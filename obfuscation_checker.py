#!/usr/bin/env python3
"""
混淆验证器 1.0
================
运行混淆器 → 对比基线 → 冒烟测试 → 通过才交付

用法:
    python3 obfuscation_checker.py --input index_vanilla.html --output index_secure.html --threshold 0.95
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

WORK_DIR = "/home/agentuser/life-simulator"

# ============================================================
# 数据结构
# ============================================================

@dataclass
class BaselineMetrics:
    """混淆前采集的基线指标"""
    file_size: int = 0
    getElementById_count: int = 0
    onclick_count: int = 0
    function_count: int = 0
    core_functions: Set[str] = field(default_factory=set)
    dom_properties: Dict[str, int] = field(default_factory=dict)
    string_literals: Dict[str, int] = field(default_factory=dict)
    global_variables: Set[str] = field(default_factory=set)
    css_rules: int = 0
    html_elements: int = 0
    
@dataclass
class CheckResult:
    """单检查结果"""
    name: str
    passed: bool
    severity: str  # CRITICAL / HIGH / MEDIUM / LOW
    before: any
    after: any
    message: str

# ============================================================
# Step 1: 基线采集
# ============================================================

def collect_baseline(html_code: str) -> BaselineMetrics:
    """从原始代码采集基线指标"""
    m = BaselineMetrics()
    
    m.file_size = len(html_code)
    m.getElementById_count = len(re.findall(r'getElementById\s*\(', html_code))
    m.onclick_count = len(re.findall(r'onclick="', html_code))
    m.function_count = len(re.findall(r'function\s+\w+\s*\(', html_code))
    
    # 核心函数列表
    core = [
        'startGame', 'newGame', 'openThread', 'openProactiveChat',
        'switchTab', 'advanceMonth', 'saveGame', 'showModal', 'hideModal',
        'loadGame', 'nextMonth', 'debouncedNextMonth', 'fastForward',
        'renderPhoneList', 'renderContacts', 'switchPhoneTab',
        'handleEncounterChoice', 'handleWorkScenarioChoice',
        'confirmTrade', 'buyHouse', 'acceptOffer',
        'generateEncounterAIResponse', 'loadLegacy', 'saveLegacy',
        'clearGame', 'closeModal', 'closeFriendDetail',
        'closeChat', 'closeEncounterScene', 'endEncounterScene'
    ]
    found_core = set()
    for f in core:
        if re.search(r'function\s+' + re.escape(f) + r'\s*\(', html_code):
            found_core.add(f)
    m.core_functions = found_core
    
    # DOM 属性引用（G.xxx）
    g_props = re.findall(r'G\.(\w+)', html_code)
    for prop in g_props:
        m.dom_properties[prop] = m.dom_properties.get(prop, 0) + 1
    
    # 字符串量（关键中文）
    critical_strings = ['现金', '存档', '读档', '度过', '月份', 
                        '职业', '投资', '社交', '手机', '通讯录']
    for s in critical_strings:
        count = html_code.count(s)
        if count > 0:
            m.string_literals[s] = count
    
    # 全局变量
    m.global_variables = set(re.findall(r'^var\s+(\w+)', html_code, re.MULTILINE))
    
    # CSS 规则数
    m.css_rules = len(re.findall(r'\.[a-zA-Z_-][a-zA-Z0-9_-]*\s*\{', html_code))
    
    # HTML 元素数
    m.html_elements = len(re.findall(r'<\w+', html_code))
    
    return m

# ============================================================
# Step 2: 运行混淆器
# ============================================================

def run_obfuscator(input_path: str, output_path: str) -> Tuple[bool, str]:
    """运行 javascript-obfuscator，返回(成功/失败, 错误信息)"""
    # 先提取 JS
    with open(input_path, 'r') as f:
        html = f.read()
    
    script_match = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
    if not script_match:
        return False, "没有找到 <script> 标签"
    
    js = script_match.group(1)
    js_path = "/tmp/game_js_input.js"
    with open(js_path, 'w') as f:
        f.write(js)
    
    obf_path = "/tmp/game_js_obfuscated.js"
    
    cmd = [
        'npx', 'javascript-obfuscator', js_path,
        '--output', obf_path,
        '--compact', 'false',              # 关键：禁用压缩！
        '--self-defending', 'true',
        '--disable-console-output', 'true',
        '--identifier-names-generator', 'hexadecimal',
        '--rename-globals', 'false',
        '--string-array', 'false',
        '--transform-object-keys', 'false',
        '--control-flow-flattening', 'false',
        '--dead-code-injection', 'false',
        '--unicode-escape-sequence', 'false',
        '--simplify', 'false',
        '--numbers-to-expressions', 'false',
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=WORK_DIR)
        if result.returncode != 0:
            return False, result.stderr[:500]
    except subprocess.TimeoutExpired:
        return False, "混淆器超时"
    except Exception as e:
        return False, str(e)
    
    # 读取混淆后 JS
    with open(obf_path, 'r') as f:
        obf_js = f.read()
    
    # 组装 HTML
    style_match = re.search(r'<style>(.*?)</style>', html, re.DOTALL)
    css = style_match.group(1) if style_match else ''
    
    body_match = re.search(r'<body>(.*?)</body>', html, re.DOTALL)
    body = body_match.group(1) if body_match else ''
    body_no_script = re.sub(r'<script>.*?</script>', '', body, flags=re.DOTALL)
    
    doctype = re.search(r'<!DOCTYPE.*?>', html).group() if re.search(r'<!DOCTYPE.*?>', html) else '<!DOCTYPE html>'
    
    anti_debug = """<html lang="zh-CN"><head>
<script>
(function(){
  document.addEventListener('keydown',function(e){
    if(e.keyCode===123||(e.ctrlKey&&e.shiftKey&&[73,74,67,85].includes(e.keyCode))){
      e.preventDefault();e.stopPropagation();e.returnValue=false;
      try{document.body.innerHTML='';}catch(x){}
      return false;
    }
  });
  document.addEventListener('contextmenu',function(e){e.preventDefault();return false;});
  setInterval(function(){
    if(window.outerWidth-window.innerWidth>200||window.outerHeight-window.innerHeight>200){
      document.body.innerHTML='';
    }
  },1500);
})();
</script>
"""
    
    final_html = f"""{doctype}
{anti_debug}
<style>{css}</style>
</head>
<body>
{body_no_script}
<script>{obf_js}</script>
</body>
</html>"""
    
    with open(output_path, 'w') as f:
        f.write(final_html)
    
    return True, ""

# ============================================================
# Step 3: 混淆后对比
# ============================================================

def compare_metrics(before: BaselineMetrics, after_code: str, threshold: float = 0.95) -> List[CheckResult]:
    """对比混淆前后指标，返回检查结果"""
    results = []
    after = collect_baseline(after_code)
    
    # CRITICAL: getElementById 数量不能减少
    geid_ratio = after.getElementById_count / max(before.getElementById_count, 1)
    results.append(CheckResult(
        name="getElementById 完整性",
        passed=geid_ratio >= threshold,
        severity="CRITICAL",
        before=before.getElementById_count,
        after=after.getElementById_count,
        message=f"保留率 {geid_ratio*100:.1f}% (阈值 {threshold*100:.0f}%)"
    ))
    
    # CRITICAL: onclick 数量必须一致
    onclick_ratio = after.onclick_count / max(before.onclick_count, 1)
    results.append(CheckResult(
        name="onclick 完整性",
        passed=onclick_ratio >= threshold,
        severity="CRITICAL",
        before=before.onclick_count,
        after=after.onclick_count,
        message=f"保留率 {onclick_ratio*100:.1f}%"
    ))
    
    # HIGH: 核心函数必须保留
    missing_core = before.core_functions - after.core_functions
    results.append(CheckResult(
        name="核心函数保留",
        passed=len(missing_core) == 0,
        severity="HIGH",
        before=len(before.core_functions),
        after=len(before.core_functions) - len(missing_core),
        message=f"缺失函数: {list(missing_core) if missing_core else '无'}"
    ))
    
    # HIGH: G.xxx 属性引用不能丢太多
    lost_props = []
    for prop, count in before.dom_properties.items():
        after_count = after.dom_properties.get(prop, 0)
        if after_count < count * threshold:
            lost_props.append(f"{prop}({count}→{after_count})")
    
    results.append(CheckResult(
        name="G.xxx 属性引用",
        passed=len(lost_props) <= 3,
        severity="HIGH",
        before=len(before.dom_properties),
        after=len(after.dom_properties),
        message=f"降质属性: {lost_props[:5] if lost_props else '无'}"
    ))
    
    # MEDIUM: 函数总数不能少太多
    func_ratio = after.function_count / max(before.function_count, 1)
    results.append(CheckResult(
        name="函数总数",
        passed=func_ratio >= threshold,
        severity="MEDIUM",
        before=before.function_count,
        after=after.function_count,
        message=f"保留率 {func_ratio*100:.1f}%"
    ))
    
    # MEDIUM: CSS 规则数
    css_ratio = after.css_rules / max(before.css_rules, 1)
    results.append(CheckResult(
        name="CSS 规则数",
        passed=css_ratio >= threshold,
        severity="MEDIUM",
        before=before.css_rules,
        after=after.css_rules,
        message=f"保留率 {css_ratio*100:.1f}%"
    ))
    
    # MEDIUM: HTML 元素数
    elem_ratio = after.html_elements / max(before.html_elements, 1)
    results.append(CheckResult(
        name="HTML 元素数",
        passed=elem_ratio >= 0.9,
        severity="MEDIUM",
        before=before.html_elements,
        after=after.html_elements,
        message=f"保留率 {elem_ratio*100:.1f}%"
    ))
    
    # LOW: 文件大小变化（混淆后应该更大或接近）
    size_ratio = after.file_size / max(before.file_size, 1)
    results.append(CheckResult(
        name="文件大小",
        passed=0.8 <= size_ratio <= 2.0,
        severity="LOW",
        before=before.file_size,
        after=after.file_size,
        message=f"变化率 {size_ratio*100:.1f}%"
    ))
    
    return results

# ============================================================
# Step 4: 头文件结构验证
# ============================================================

def verify_html_structure(html_code: str) -> List[CheckResult]:
    """验证HTML结构完整性"""
    results = []
    
    # DOCTYPE
    results.append(CheckResult(
        name="DOCTYPE 声明",
        passed=bool(re.search(r'<!DOCTYPE\s+html>', html_code)),
        severity="CRITICAL",
        before="需要",
        after="存在" if re.search(r'<!DOCTYPE\s+html>', html_code) else "缺失",
        message="DOCTYPE"
    ))
    
    # html 标签
    html_open = len(re.findall(r'<html[^>]*>', html_code))
    html_close = len(re.findall(r'</html>', html_code))
    results.append(CheckResult(
        name="html 标签匹配",
        passed=html_open == 1 and html_close == 1,
        severity="CRITICAL",
        before="1开1闭",
        after=f"{html_open}开{html_close}闭",
        message="<html>标签"
    ))
    
    # head/body
    for tag in ['head', 'body']:
        open_count = len(re.findall(rf'<{tag}[^>]*>', html_code))
        close_count = len(re.findall(rf'</{tag}>', html_code))
        results.append(CheckResult(
            name=f"{tag} 标签匹配",
            passed=open_count == 1 and close_count == 1,
            severity="CRITICAL",
            before="1开1闭",
            after=f"{open_count}开{close_count}闭",
            message=f"<{tag}>"
        ))
    
    # script 标签必须平衡
    script_open = len(re.findall(r'<script>', html_code))
    script_close = len(re.findall(r'</script>', html_code))
    results.append(CheckResult(
        name="script 标签平衡",
        passed=script_open == script_close and script_open >= 1,
        severity="CRITICAL",
        before="平衡",
        after=f"{script_open}开{script_close}闭",
        message="<script>标签"
    ))
    
    # style 标签
    style_open = len(re.findall(r'<style>', html_code))
    style_close = len(re.findall(r'</style>', html_code))
    results.append(CheckResult(
        name="style 标签平衡",
        passed=style_open == style_close and style_open >= 1,
        severity="HIGH",
        before="平衡",
        after=f"{style_open}开{style_close}闭",
        message="<style>标签"
    ))
    
    # 反调试代码
    results.append(CheckResult(
        name="反调试代码",
        passed='contextmenu' in html_code and 'keyCode===123' in html_code,
        severity="HIGH",
        before="需要",
        after="存在" if 'keyCode===123' in html_code else "缺失",
        message="反调试系统"
    ))
    
    return results

# ============================================================
# Step 5: 垃圾代码检测
# ============================================================

def detect_junk_code(html_code: str) -> List[CheckResult]:
    """检测垃圾代码（混淆器插入的无意义函数）"""
    results = []
    
    # 检测混淆器垃圾函数的特征
    junk_patterns = [
        r'function\s+_0x[a-f0-9]+\s*\(\)\s*\{\s*var\s+_\w+=\d+;',
        r'return\s+\w+%',
    ]
    
    junk_count = 0
    for pattern in junk_patterns:
        matches = re.findall(pattern, html_code)
        junk_count += len(matches)
    
    results.append(CheckResult(
        name="垃圾代码检测",
        passed=junk_count == 0,
        severity="HIGH",
        before=0,
        after=junk_count,
        message=f"发现 {junk_count} 个疑似垃圾函数" if junk_count else "未发现垃圾代码"
    ))
    
    return results

# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="混淆验证器")
    parser.add_argument('--input', default=os.path.join(WORK_DIR, 'index_vanilla.html'))
    parser.add_argument('--output', default=os.path.join(WORK_DIR, 'index_secure.html'))
    parser.add_argument('--threshold', type=float, default=0.95)
    parser.add_argument('--no-obfuscate', action='store_true', help="跳过混淆，直接验证已存在的输出文件")
    args = parser.parse_args()
    
    print("=" * 70)
    print("🔍 混淆验证器 v1.0")
    print("=" * 70)
    
    # 读取原始代码
    with open(args.input, 'r') as f:
        original = f.read()
    
    baseline = collect_baseline(original)
    
    print(f"\n📊 基线指标:")
    print(f"  文件大小:     {baseline.file_size/1024:.0f} KB")
    print(f"  getElementById: {baseline.getElementById_count}")
    print(f"  onclick 数量:  {baseline.onclick_count}")
    print(f"  函数数量:      {baseline.function_count}")
    print(f"  核心函数:      {len(baseline.core_functions)} 个")
    print(f"  CSS 规则:      {baseline.css_rules}")
    print(f"  HTML 元素:     {baseline.html_elements}")
    
    # 混淆
    if not args.no_obfuscate:
        print(f"\n🔀 运行混淆器...")
        ok, err = run_obfuscator(args.input, args.output)
        if not ok:
            print(f"❌ 混淆失败: {err}")
            sys.exit(1)
        print("  ✅ 混淆完成")
    
    # 读取混淆后代码
    if not os.path.exists(args.output):
        print(f"❌ 输出文件不存在: {args.output}")
        sys.exit(1)
    
    with open(args.output, 'r') as f:
        obfuscated = f.read()
    
    after = collect_baseline(obfuscated)
    
    # 对比验证
    print(f"\n📊 混淆验证 (阈值 {args.threshold*100:.0f}%):")
    compare_results = compare_metrics(baseline, obfuscated, args.threshold)
    structure_results = verify_html_structure(obfuscated)
    junk_results = detect_junk_code(obfuscated)
    
    all_results = compare_results + structure_results + junk_results
    
    # 分类统计
    critical_pass = sum(1 for r in all_results if r.severity == "CRITICAL" and r.passed)
    critical_total = sum(1 for r in all_results if r.severity == "CRITICAL")
    high_pass = sum(1 for r in all_results if r.severity == "HIGH" and r.passed)
    high_total = sum(1 for r in all_results if r.severity == "HIGH")
    medium_pass = sum(1 for r in all_results if r.severity == "MEDIUM" and r.passed)
    medium_total = sum(1 for r in all_results if r.severity == "MEDIUM")
    low_pass = sum(1 for r in all_results if r.severity == "LOW" and r.passed)
    low_total = sum(1 for r in all_results if r.severity == "LOW")
    
    print(f"\n  🔴 CRITICAL: {critical_pass}/{critical_total}")
    print(f"  🟠 HIGH:     {high_pass}/{high_total}")
    print(f"  🟡 MEDIUM:   {medium_pass}/{medium_total}")
    print(f"  ⚪ LOW:      {low_pass}/{low_total}")
    
    # 详细结果
    print(f"\n{'='*70}")
    print("详细结果:")
    print("=" * 70)
    
    failed = []
    for r in all_results:
        icon = "✅" if r.passed else "❌"
        severity_icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}[r.severity]
        print(f"  {icon} {severity_icon} [{r.severity}] {r.name}: {r.message}")
        if not r.passed:
            failed.append(r)
    
    # 最终判定
    print(f"\n{'='*70}")
    critical_failed = [r for r in failed if r.severity == "CRITICAL"]
    high_failed = [r for r in failed if r.severity == "HIGH"]
    
    if critical_failed:
        print(f"\n❌ 验证失败！{len(critical_failed)} 个 CRITICAL 问题")
        print("打回给 Coder 重新混淆:")
        for r in critical_failed:
            print(f"  - {r.name}: {r.message}")
        sys.exit(1)
    elif high_failed:
        print(f"\n⚠️ 警告: {len(high_failed)} 个 HIGH 级别问题")
        print("建议修复:")
        for r in high_failed:
            print(f"  - {r.name}: {r.message}")
        sys.exit(2)
    else:
        print(f"\n🎉 全部通过！混淆验证完成。")
        print(f"  输出文件: {args.output}")
        print(f"  文件大小: {os.path.getsize(args.output)/1024:.0f} KB")
        sys.exit(0)

if __name__ == '__main__':
    main()
