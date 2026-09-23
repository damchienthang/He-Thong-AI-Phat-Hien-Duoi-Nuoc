"""Optional browser checks: pip install playwright, using installed MS Edge.

Run from project root: python docs/check_dashboard.py.
Controlled predictions here are test fixtures, not research results.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

with sync_playwright() as driver:
    browser = driver.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    messages, routes = [], []
    def websocket(route):
        routes.append(route)
        route.on_message(lambda message: messages.append(json.loads(message)))
    page.route_web_socket("ws://localhost:8000/ws/monitor", websocket)
    page.set_default_timeout(10000)
    page.goto((ROOT / "frontend/index.html").as_uri())
    assert page.locator("#total").inner_text() == "—"
    assert page.locator('.tab').all_text_contents() == [
        '▦ Dashboard', '♧ Alert History', '⚙ Settings']
    assert page.locator('#results, #resultFile').count() == 0
    page.locator('[data-tab="history"]').click()
    assert page.locator('#exportLog').is_visible()
    page.locator('[data-tab="settings"]').click()
    page.locator("#connect").click()
    page.wait_for_function("document.getElementById('disconnect').disabled === false")
    frame = {"type": "frame", "version": 1, "stream_id": "test", "video_time": 0,
             "model": "TEST FIXTURE", "is_demo": True, "persons": [
                 {"id": 1, "label": "drowning", "confidence": .9, "duration": 20,
                  "box": [.1, .1, .4, .7], "state": "CRITICAL", "event_id": "test-1"}]}
    routes[0].send(json.dumps(frame))
    page.wait_for_function("document.getElementById('danger').textContent === '1'")
    page.locator("#alerts .rescue").click()
    page.wait_for_timeout(100)
    assert messages[0]["type"] == "acknowledge"
    assert page.locator("#alerts .rescue").is_disabled()
    routes[0].send(json.dumps({"type": "acknowledged", "version": 1,
                              "stream_id": "test", "event_id": "test-1", "person_id": 1}))
    page.wait_for_function("document.querySelector('#alerts .rescue').textContent.includes('Backend')")
    frame['persons'][0]['event_id'] = 'test-2'
    routes[0].send(json.dumps(frame))
    page.wait_for_function("document.querySelector('#alerts .false-alarm').disabled === false")
    page.locator('#alerts .false-alarm').click()
    page.wait_for_timeout(100)
    assert messages[-1]['action'] == 'false_alarm'
    routes[0].send(json.dumps({'type':'acknowledged','version':1,'stream_id':'test',
                              'event_id':'test-2','person_id':1,'action':'false_alarm'}))
    page.wait_for_function("document.querySelector('#alerts .rescue').textContent.includes('báo giả')")
    assert page.locator('#heatmapEmpty').is_hidden()
    assert page.locator('#frequencyEmpty').is_hidden()
    page.evaluate("lastReceived = performance.now() - 4000")
    page.wait_for_function("document.getElementById('total').textContent === '—'")
    page.locator('[data-tab="settings"]').click()
    page.locator("#disconnect").click()
    page.locator("#file").set_input_files(str(ROOT / "assets/demo/outdoor_pool.webm"))
    page.wait_for_function("document.getElementById('video').readyState >= 1")
    assert page.evaluate("video.videoWidth > 0")
    page.reload()
    page.locator('#file').set_input_files(str(ROOT / 'assets/demo/outdoor_pool.webm'))
    page.wait_for_function("video.readyState >= 2")
    page.evaluate("async () => {video.muted = true; await video.play();}")
    page.wait_for_function("video.currentTime > .5")
    page.evaluate("video.pause()")
    page.screenshot(path=str(ROOT / 'docs/dashboard-preview.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    page.locator('[data-tab="settings"]').click()
    assert page.locator('#connect').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
    assert not errors, errors
    browser.close()
print("PASS: task 3.2 navigation, desktop/mobile layout, video playback, WebSocket, rescue/false-alarm ACK, stale data, charts.")
