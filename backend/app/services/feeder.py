"""馈线巡检业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "feeder"
REQUIRED_FIELDS = ["馈线编号", "所属站点", "馈线长度"]
ENTRY_FIELDS = ["馈线编号", "所属站点", "馈线长度", "接头数量", "防水情况", "接地电阻", "巡检日期", "馈线状态"]
STATUS_ORDER = ["正常", "防水失效", "接地超标", "已修复"]
ACTION_RULES = {"登记失效": "防水失效", "登记超标": "接地超标", "安排修复": "已修复"}
NEGATIVE_ACTIONS = ["登记失效", "登记超标"]


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
            rows = [row for row in rows if keyword in str(row.get("馈线编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
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
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        # 登记内容整体落地：接头数量、巡检日期等字段跟必填项一起存，不再只留必填三项
        for field in ENTRY_FIELDS:
            value = values.get(field)
            if value is not None and str(value).strip() != "":
                entry[field] = value
        entry.setdefault("馈线状态", STATUS_ORDER[0])
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"馈线 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于馈线巡检可执行范围"
        target = ACTION_RULES[action]
        current = str(entry.get("status") or STATUS_ORDER[0])
        if current not in STATUS_ORDER:
            return None, f"馈线当前状态「{current}」不在允许的状态序列里，请先核对登记内容"
        # 状态只能顺着 正常→防水失效→接地超标→已修复 往前走，不许往回走
        if STATUS_ORDER.index(target) <= STATUS_ORDER.index(current):
            return None, (
                f"馈线当前为「{current}」，只能顺着{'→'.join(STATUS_ORDER)}往前走，"
                f"不能{action}退回「{target}」"
            )
        entry["status"] = target
        entry["馈线状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        # 修复处理收口：登记失效把防水情况坐实为失效，安排修复把失效的防水关掉
        if action == "登记失效":
            entry["防水情况"] = "失效"
        elif action == "安排修复" and entry.get("防水情况") == "失效":
            entry["防水情况"] = "已修复"
        return entry, f"馈线已{action}，当前状态「{target}」"
