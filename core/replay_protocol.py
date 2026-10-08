"""营地官方回顾页面确认的坐标、采样与事件约定。

来源：https://camp.qq.com/h5/webdist/battle-replay/static/js/main.b6a0acd6.js
2026-10-08 核对：轨迹每秒一点；事件时间为毫秒；地图坐标跨度为 108。
"""

MAP_IMAGE_URL = "https://camp.qq.com/meta-data/heros/battle-replay-map.jpg"
MAP_HALF_SIZE = 54.0
POSITION_INTERVAL_SECONDS = 1
ECONOMY_INTERVAL_SECONDS = 30
RESOURCE_NAMES = {
    8: "主宰",
    9: "暴君",
    10: "蓝 buff",
    11: "红 buff",
    17: "暗影暴君",
    26: "先知小主宰",
    28: "风暴龙王",
}
# 官方 bs/ws 与 ko/Co 对应的分路和塔序名称。
ROAD_NAMES = {0: "下路", 1: "中路", 2: "上路"}
TOWER_NAMES = {0: "高地塔", 1: "二塔", 2: "一塔"}

# 官方 TowerConf 的数组顺序为阵营、分路、塔序，不能复用其他接口的分路枚举。
TOWER_POSITIONS = (
    (
        ((-25, -49), (-3, -49), (23, -49)),
        ((-32, -33), (-20, -23), (-12, -9)),
        ((-49, -25), (-50, -7), (-50, 23)),
    ),
    (
        ((49, 24), (50, 7), (50, -23)),
        ((32, 32), (20, 23), (12, 9)),
        ((25, 47), (7, 49), (-23, 49)),
    ),
)
