/**
 * 카드뉴스 자동 생성 피그마 플러그인
 * 로컬 서버(http://localhost:8765)에서 카드 데이터를 받아
 * 마스터 프레임을 복제하고 텍스트/이미지를 교체합니다.
 */

const SERVER_URL = "http://localhost:8765";

// ── 마스터 프레임 이름 ─────────────────────────────────────────
const MASTER_FRAMES = {
  thumbnail: "마스터_썸네일",
  body1: "마스터_본문_1",
  body2: "마스터_본문_2",
  body3: "마스터_본문_3",
  cta: "마스터_CTA",
};

// ── 마스터 프레임 찾기 ─────────────────────────────────────────
function findMasterFrame(name) {
  const nodes = figma.currentPage.findAll(
    (n) => n.type === "FRAME" && n.name === name
  );
  if (nodes.length === 0) {
    figma.notify(`마스터 프레임 "${name}"을 찾을 수 없습니다.`, { error: true });
    return null;
  }
  return nodes[0];
}

// ── 프레임 내 텍스트 노드를 DFS 순서로 수집 ────────────────────
function collectTextNodes(node) {
  const texts = [];
  function dfs(n) {
    if (n.type === "TEXT") {
      texts.push(n);
    }
    if ("children" in n) {
      for (const child of n.children) {
        dfs(child);
      }
    }
  }
  dfs(node);
  return texts;
}

// ── 프레임 내 이미지 채우기가 있는 노드 찾기 ────────────────────
function findImageFillNode(node) {
  // 배경 이미지를 가진 첫 번째 노드를 찾음 (보통 프레임 자체 또는 Rectangle)
  function dfs(n) {
    if (n.fills && Array.isArray(n.fills)) {
      for (const fill of n.fills) {
        if (fill.type === "IMAGE") {
          return n;
        }
      }
    }
    if ("children" in n) {
      for (const child of n.children) {
        const found = dfs(child);
        if (found) return found;
      }
    }
    return null;
  }
  return dfs(node);
}

// ── 이미지 설정 ────────────────────────────────────────────────
async function setImageFill(node, imageBase64) {
  const imageBytes = figma.base64Decode(imageBase64);
  const image = figma.createImage(imageBytes);
  const fills = JSON.parse(JSON.stringify(node.fills));
  // 기존 이미지 fill을 교체
  let replaced = false;
  for (let i = 0; i < fills.length; i++) {
    if (fills[i].type === "IMAGE") {
      fills[i].imageHash = image.hash;
      fills[i].scaleMode = "FILL";
      replaced = true;
      break;
    }
  }
  if (!replaced) {
    fills.push({
      type: "IMAGE",
      imageHash: image.hash,
      scaleMode: "FILL",
    });
  }
  node.fills = fills;
}

// ── 텍스트 설정 (폰트 로드 포함) ───────────────────────────────
async function setTextContent(textNode, content) {
  try {
    const fontName = textNode.fontName;
    if (fontName !== figma.mixed) {
      await figma.loadFontAsync(fontName);
    } else {
      const firstFont = textNode.getRangeFontName(0, 1);
      await figma.loadFontAsync(firstFont);
    }
  } catch (e) {
    // 폰트 로드 실패 시 기본 폰트로 대체
    try {
      await figma.loadFontAsync({ family: "Inter", style: "Regular" });
      textNode.fontName = { family: "Inter", style: "Regular" };
    } catch (e2) {
      await figma.loadFontAsync({ family: "Roboto", style: "Regular" });
      textNode.fontName = { family: "Roboto", style: "Regular" };
    }
  }
  textNode.characters = content;
}

// ── 단일 카드 세트 생성 (5장) ──────────────────────────────────
async function createCardSet(setData, offsetX) {
  const CARD_WIDTH = 1080;
  const CARD_HEIGHT = 1350;
  const GAP = 50;
  const createdFrames = [];

  // Card01 — 썸네일
  const masterThumb = findMasterFrame(MASTER_FRAMES.thumbnail);
  if (!masterThumb) return [];
  const card01 = masterThumb.clone();
  card01.name = `${setData.angle}_Card01`;
  card01.x = offsetX;
  card01.y = 2000; // 마스터 프레임 아래에 배치

  const thumbTexts = collectTextNodes(card01);
  if (thumbTexts.length >= 1) await setTextContent(thumbTexts[0], setData.card01.headline);
  if (thumbTexts.length >= 2) await setTextContent(thumbTexts[1], setData.card01.chip2);
  if (thumbTexts.length >= 3) await setTextContent(thumbTexts[2], setData.card01.chip1);
  if (thumbTexts.length >= 4) await setTextContent(thumbTexts[3], "");

  // 배경 이미지 교체 (카드별 개별 이미지)
  const thumbImgNode = findImageFillNode(card01);
  if (thumbImgNode && setData.background_images && setData.background_images.card01) {
    await setImageFill(thumbImgNode, setData.background_images.card01);
  }
  card01.clipsContent = true;
  createdFrames.push(card01);

  // Card02 — 본문 1 (마스터_본문_1)
  const masterBody1 = findMasterFrame(MASTER_FRAMES.body1);
  if (masterBody1) {
    const card02 = masterBody1.clone();
    card02.name = `${setData.angle}_Card02`;
    card02.x = offsetX + (CARD_WIDTH + GAP);
    card02.y = 2000;

    const body1Texts = collectTextNodes(card02);
    if (body1Texts.length >= 1) await setTextContent(body1Texts[0], setData.card02.section_title);
    if (body1Texts.length >= 2) await setTextContent(body1Texts[1], setData.card02.input_text);
    if (body1Texts.length >= 3) await setTextContent(body1Texts[2], "");

    const body1ImgNode = findImageFillNode(card02);
    if (body1ImgNode && setData.background_images && setData.background_images.card02) {
      await setImageFill(body1ImgNode, setData.background_images.card02);
    }
    card02.clipsContent = true;
    createdFrames.push(card02);
  }

  // Card03 — 본문 2 (마스터_본문_2)
  const masterBody2 = findMasterFrame(MASTER_FRAMES.body2);
  if (masterBody2) {
    const card03 = masterBody2.clone();
    card03.name = `${setData.angle}_Card03`;
    card03.x = offsetX + (CARD_WIDTH + GAP) * 2;
    card03.y = 2000;

    const body2Texts = collectTextNodes(card03);
    if (body2Texts.length >= 1) await setTextContent(body2Texts[0], setData.card03.section_title);
    if (body2Texts.length >= 2) await setTextContent(body2Texts[1], setData.card03.input_text);
    if (body2Texts.length >= 3) await setTextContent(body2Texts[2], "");

    const body2ImgNode = findImageFillNode(card03);
    if (body2ImgNode && setData.background_images && setData.background_images.card03) {
      await setImageFill(body2ImgNode, setData.background_images.card03);
    }
    card03.clipsContent = true;
    createdFrames.push(card03);
  }

  // Card04 — 본문 3 (마스터_본문_3)
  const masterBody3 = findMasterFrame(MASTER_FRAMES.body3);
  if (masterBody3) {
    const card04 = masterBody3.clone();
    card04.name = `${setData.angle}_Card04`;
    card04.x = offsetX + (CARD_WIDTH + GAP) * 3;
    card04.y = 2000;

    const body3Texts = collectTextNodes(card04);
    if (body3Texts.length >= 1) await setTextContent(body3Texts[0], setData.card04.section_title);
    if (body3Texts.length >= 2) await setTextContent(body3Texts[1], setData.card04.input_text);
    if (body3Texts.length >= 3) await setTextContent(body3Texts[2], "");

    const body3ImgNode = findImageFillNode(card04);
    if (body3ImgNode && setData.background_images && setData.background_images.card04) {
      await setImageFill(body3ImgNode, setData.background_images.card04);
    }
    card04.clipsContent = true;
    createdFrames.push(card04);
  }

  // Card05 — CTA (마스터_CTA, 배경 이미지 교체 안 함)
  const masterCTA = findMasterFrame(MASTER_FRAMES.cta);
  if (masterCTA) {
    const card05 = masterCTA.clone();
    card05.name = `${setData.angle}_Card05_CTA`;
    card05.x = offsetX + (CARD_WIDTH + GAP) * 4;
    card05.y = 2000;

    const ctaTexts = collectTextNodes(card05);
    // CTA 프레임의 모든 "CTA 문구를 입력해주세요." 텍스트를 교체
    for (const t of ctaTexts) {
      if (t.characters.includes("CTA") || t.characters.includes("입력해주세요")) {
        await setTextContent(t, setData.card05_cta || "더 많은 콘텐츠 보러가기");
      }
    }

    card05.clipsContent = true;
    createdFrames.push(card05);
  }

  return createdFrames;
}

// ── 서버 완료 알림 ─────────────────────────────────────────────
async function notifyServerComplete(rowIndex) {
  try {
    const res = await fetch(`${SERVER_URL}/api/complete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ row_index: rowIndex }),
    });
    return res.ok;
  } catch (e) {
    console.error("서버 알림 실패:", e);
    return false;
  }
}

// ── 마스터 프레임에서 사용하는 폰트 미리 로드 ───────────────────
async function preloadFonts() {
  const masterNames = Object.values(MASTER_FRAMES);
  const fontSet = new Set();
  for (const name of masterNames) {
    const frame = figma.currentPage.findOne((n) => n.type === "FRAME" && n.name === name);
    if (!frame) continue;
    const texts = collectTextNodes(frame);
    for (const t of texts) {
      const fn = t.fontName;
      if (fn !== figma.mixed) {
        fontSet.add(JSON.stringify(fn));
      }
    }
  }
  for (const fnStr of fontSet) {
    try {
      await figma.loadFontAsync(JSON.parse(fnStr));
    } catch (e) {
      console.log("폰트 로드 실패:", fnStr);
    }
  }
}

// ── 메인 실행 ──────────────────────────────────────────────────
async function main() {
  figma.notify("폰트 로딩 중...");
  await preloadFonts();

  figma.notify("서버에서 카드 데이터를 가져오는 중...");

  let data;
  try {
    const res = await fetch(`${SERVER_URL}/api/cards`);
    if (!res.ok) throw new Error(`서버 응답 오류: ${res.status}`);
    data = await res.json();
  } catch (e) {
    figma.notify(
      `서버 연결 실패. python pipeline.py serve 를 먼저 실행하세요.`,
      { error: true }
    );
    figma.closePlugin();
    return;
  }

  const sets = data.sets || [];
  if (sets.length === 0) {
    figma.notify("생성할 카드 세트가 없습니다.");
    figma.closePlugin();
    return;
  }

  figma.notify(`${sets.length}개 세트 생성 중...`);

  const SET_Y_GAP = 1600;
  const allFrames = [];

  for (let i = 0; i < sets.length; i++) {
    const setData = sets[i];
    const offsetX = 0;

    // 각 세트를 Y축으로 분리
    const frames = await createCardSet(setData, offsetX);

    // Y 위치 조정 (세트별로 아래로)
    for (const f of frames) {
      f.y = 2000 + i * SET_Y_GAP;
    }
    allFrames.push(...frames);

    // 서버에 완료 알림
    await notifyServerComplete(setData.row_index);
  }

  // 생성된 프레임 선택
  figma.currentPage.selection = allFrames;
  if (allFrames.length > 0) {
    figma.viewport.scrollAndZoomIntoView(allFrames);
  }

  figma.notify(`${sets.length}개 세트 (${allFrames.length}장) 생성 완료!`);
  figma.closePlugin();
}

main();
