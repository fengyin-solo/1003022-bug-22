"""馈线巡检业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "feeder"
# 必填项：缺哪一项都要在返回里点名，不许静默丢字段
REQUIRED_FIELDS = ["馈线编号", "所属站点", "馈线长度"]
# 登记/修改时一并落地的巡检内容，接头数量和巡检日期也在其中
EDITABLE_FIELDS = ["馈线编号", "所属站点", "馈线长度", "接头数量", "防水情况", "接地电阻", "巡检日期"]
STATUS_ORDER = ["正常", "防水失效", "接地超标", "已修复"]
ACTION_RULES = {"登记失效": "防水失效", "登记超标": "接地超标", "安排修复": "已修复"}
# 每个动作允许的出发状态：状态只能沿 STATUS_ORDER 往前走，不许回退
ACTION_FROM = {
    "登记失效": {"正常"},
    "登记超标": {"正常", "防水失效"},
    "安排修复": {"防水失效", "接地超标"},
}
ABNORMAL_STATUS = {"防水失效", "接地超标"}


class FeederService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            keyword = keyword.strip()
            rows = [row for row in rows if keyword in str(row.get("馈线编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        # 先按条件筛全量、再分页：total 与筛选后的条数始终同一口径
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        # 只收录实际提交的字段，没提交的由下面的默认值兜底，避免落成 None
        entry.update({
            field: values[field]
            for field in EDITABLE_FIELDS
            if values.get(field) is not None
        })
        entry.setdefault("接头数量", "")
        entry.setdefault("防水情况", "正常")
        entry.setdefault("接地电阻", "合格")
        entry["巡检日期"] = str(values.get("巡检日期") or "").strip() or date.today().isoformat()
        entry["status"] = STATUS_ORDER[0]
        entry["馈线状态"] = entry["status"]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def update_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, []  # 不存在由路由层给 404
        missing = [
            field
            for field in REQUIRED_FIELDS
            if not str(values.get(field, entry.get(field)) or "").strip()
        ]
        if missing:
            return None, missing
        # 登记内容原地落地，接头数量、巡检日期改完即存，状态仍由动作接口推进
        for field in EDITABLE_FIELDS:
            if field in values:
                entry[field] = values[field]
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"馈线 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于馈线巡检可执行范围"
        current = str(entry.get("status") or "")
        if current not in STATUS_ORDER:
            return None, f"馈线当前状态「{current}」不在允许的状态序列里"
        target = ACTION_RULES[action]
        cur_idx = STATUS_ORDER.index(current)
        target_idx = STATUS_ORDER.index(target)
        if current not in ACTION_FROM[action] or target_idx <= cur_idx:
            # 收口：只能沿 正常 → 防水失效 → 接地超标 → 已修复 前进，不许往回走
            chain = " → ".join(STATUS_ORDER)
            if current == STATUS_ORDER[-1]:
                return None, f"馈线已修复归档，不能再执行「{action}」"
            return None, f"馈线当前为「{current}」，不能回退执行「{action}」（状态只能沿 {chain} 前进）"
        entry["status"] = target
        entry["馈线状态"] = target
        # 修复动作必须收口：防水、接地两项一并恢复，异常记录真正退出异常
        if action == "登记失效":
            entry["防水情况"] = "失效"
        elif action == "登记超标":
            entry["接地电阻"] = "超标"
        elif action == "安排修复":
            entry["防水情况"] = "正常"
            entry["接地电阻"] = "合格"
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = target in ABNORMAL_STATUS
        return entry, f"馈线已{action}"
