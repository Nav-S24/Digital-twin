import numpy as np, pandas as pd
from src.config import *
from src.utils import get_logger

logger = get_logger(__name__)

def compute_engine_health(df):
    score = pd.Series(100.0, index=df.index)
    t,p,r,v,fc = df["temperature"],df["pressure"],df["rpm"],df["vibration"],df["fault_count"]
    et,pw = ENGINE_THRESHOLDS, ENGINE_PENALTY_WEIGHTS
    for col, val, direction in [
        ("temperature", t, "high"), ("pressure", p, "low"),
        ("rpm", r, "high"), ("vibration", v, "high")]:
        if direction == "high":
            opt = et[col]["optimal_max"]; warn = et[col]["warning"]; crit = et[col]["critical"]
            pen = np.where(val<=opt, 0,
                  np.where(val<=warn, pw[col]*(val-opt)/(warn-opt),
                  np.where(val<=crit, pw[col], pw[col]*1.5)))
        else:
            opt = et[col]["optimal_min"]; warn = et[col]["warning"]; crit = et[col]["critical"]
            pen = np.where(val>=opt, 0,
                  np.where(val>=warn, pw[col]*(opt-val)/(opt-warn),
                  np.where(val>=crit, pw[col], pw[col]*1.5)))
        score -= pen
    fc_warn,fc_crit = et["fault_count"]["warning"],et["fault_count"]["critical"]
    score -= np.where(fc<=fc_warn, 0,
             np.where(fc<=fc_crit, pw["fault_count"]*(fc-fc_warn)/(fc_crit-fc_warn), pw["fault_count"]))
    return score.clip(0,100).rename("engine_health")

def compute_battery_health(df):
    score = pd.Series(100.0, index=df.index)
    bt = BATTERY_THRESHOLDS
    v,c,bt_temp = df["battery_voltage"],df["battery_current"],df["battery_temp"]
    v_nom,v_warn,v_crit = bt["voltage"]["nominal"],bt["voltage"]["warning"],bt["voltage"]["critical"]
    score -= np.where(v>=v_nom, 0, np.where(v>=v_warn, 33*(v_nom-v)/(v_nom-v_warn),
             np.where(v>=v_crit, 33, 50)))
    c_max,c_warn,c_crit = bt["current"]["max_draw"],bt["current"]["warning"],bt["current"]["critical"]
    score -= np.where(c<=c_warn, 0, np.where(c<=c_max, 33*(c-c_warn)/(c_max-c_warn),
             np.where(c<=c_crit, 33, 50)))
    bt_opt,bt_warn,bt_crit = bt["temp"]["optimal_max"],bt["temp"]["warning"],bt["temp"]["critical"]
    score -= np.where(bt_temp<=bt_opt, 0, np.where(bt_temp<=bt_warn, 34*(bt_temp-bt_opt)/(bt_warn-bt_opt),
             np.where(bt_temp<=bt_crit, 34, 50)))
    return score.clip(0,100).rename("battery_health")

def compute_vehicle_health(engine_health, battery_health):
    w = VEHICLE_HEALTH_WEIGHTS
    return (w["engine"]*engine_health + w["battery"]*battery_health).clip(0,100).rename("vehicle_health")

def assign_health_class(vehicle_health):
    def _c(s):
        for lb,lbl,cid in HEALTH_CLASS_MAP:
            if s >= lb: return lbl,cid
        return "Critical",3
    res = vehicle_health.apply(_c)
    return pd.DataFrame(res.tolist(), columns=["health_class","health_class_id"], index=vehicle_health.index)

def compute_trip_readiness(df):
    w = TRIP_READINESS_WEIGHTS
    fault_term = (100 - df["fault_count"]*w["fault_multiplier"]).clip(0,100)
    score = (w["vehicle_health"]*df["vehicle_health"] +
             w["battery_health"]*df["battery_health"] +
             w["fault_penalty"]*fault_term).clip(0,100)
    def _lbl(s):
        for t,l in TRIP_READINESS_LABELS:
            if s >= t: return l
        return "Not Recommended"
    return pd.DataFrame({"trip_readiness":score,"trip_readiness_label":score.apply(_lbl)}, index=df.index)

def add_all_health_scores(df):
    df = df.copy()
    df["engine_health"]  = compute_engine_health(df)
    df["battery_health"] = compute_battery_health(df)
    df["vehicle_health"] = compute_vehicle_health(df["engine_health"], df["battery_health"])
    df = pd.concat([df, assign_health_class(df["vehicle_health"])], axis=1)
    df = pd.concat([df, compute_trip_readiness(df)], axis=1)
    return df