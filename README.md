# Chord Harmony Generator 和弦聲部生成器

---

## 繁體中文

本專案是一個小型 Python 應用程式，功能如下：

- **以文字輸入和弦進行**
- **生成四部（或更多部）和聲**，並做到：
  - 符合所輸入的和弦
  - 各聲部維持在適當音域
  - 偏好級進進行
  - 避免大跳與聲部交叉
  - 對平行五度／八度施加懲罰（基本古典風格聲部進行）

核心邏輯在 `harmony.py`，以簡單搜尋方式為每個和弦選出能將「從上一個和弦到此和弦」的聲部進行成本最小化的排列。

> 這**不是**完整的聖詠式引擎，而是一個可依需求調整與擴充的實用起點。

### 快速開始（不需會程式或指令）

**在 Windows 上**，若你**沒用過指令列、不知道什麼是 Bash 或程式**，可以完全用滑鼠操作：

1. **第一次使用前：設定一次**
   - 在檔案總管中打開本程式的資料夾 `chord-harmony-generator`。
   - 找到 **`setup_harmony_app.bat`**，用滑鼠**連點兩下**執行。
   - 會跳出一個黑色視窗並自動安裝所需檔案，請**等它跑完**（看到「完成」或視窗關閉為止）。只需做這一次，之後不用重複。

2. **每次要使用程式時**
   - 在同一資料夾裡找到 **`launch_harmony_web.bat`**，用滑鼠**連點兩下**執行。
   - 通常會自動開啟瀏覽器並進入和聲生成器頁面；若沒有，請自己打開瀏覽器，在網址列輸入：`http://127.0.0.1:5001/` 後按 Enter。

3. **在網頁裡**
   - 在「和弦進行」欄位輸入和弦（例如：`C | F | G7 | C`），選擇聲部數量，按 **Generate Harmony**，即可看到各聲部與鋼琴捲簾，並可下載 MIDI。

不需要安裝 Python、不需要打任何指令，只要會雙擊檔案和用瀏覽器即可。（若使用 Mac 或 Linux，請改看下方「安裝」與「網頁介面使用」的終端機步驟。）

### 安裝（使用輔助腳本）

在 `chord-harmony-generator` 目錄下可使用提供的 Windows 設定腳本：

```bash
setup_harmony_app.bat
```

腳本會：

- 在 `.venv` 建立虛擬環境（若尚未存在）
- 啟動虛擬環境
- 依 `requirements.txt` 安裝所需 Python 套件

若欲手動安裝：

```bash
cd chord-harmony-generator
python -m venv .venv
.\.venv\Scripts\activate  # Windows
```

再安裝依賴：

```bash
pip install -r requirements.txt
```

### 命令列使用

執行 CLI：

```bash
python main.py
```

程式會依序詢問：

- **聲部數量**（例如 `4` 表示四部）
- **和弦進行**，例如：

```text
Cmaj | Fmaj | G7 | Cmaj
```

或：

```text
Am | Dm | G | C
```

程式會印出各聲部在整段進行上的簡單文字表示。若已安裝 `music21`（列於 `requirements.txt`），還會在同一資料夾寫入名為 `output.mid` 的 MIDI 檔。

### 網頁介面使用

另提供以 Flask 建置的小型網頁介面。

1. 先完成環境設定（執行一次 `setup_harmony_app.bat`）。
2. 啟動網頁介面：

```bash
launch_harmony_web.bat
```

3. 在瀏覽器開啟 `http://127.0.0.1:5001/`（若未自動開啟）。

介面上可設定：

- **聲部數量**（4–6）
- **和弦進行**文字框
- **Generate Harmony** 按鈕會計算並顯示：
  - 和弦序列
  - 各聲部（由高到低）以表格顯示的音名
- 若已安裝 `music21`，會顯示 **Download MIDI** 連結以下載 `output.mid`。

#### 鎖定與 What-if（排列控制）

生成後，每個和弦欄位提供：

- **Lock**：勾選可固定該和弦目前的排列，再按 **Generate** 會以鎖定的和弦為準重新優化其餘進行。
- **What if**：展開可查看該和弦的其他佳選排列（依局部聲部進行成本評分），點 **Use this** 可採用該排列並重新執行優化。

### 和弦記譜

**根音**（大小寫皆可，含升、降記號）：

`C C# Db D D# Eb E F F# Gb G G# Ab A A# Bb B`

**常用品質／符號**（非窮舉，但涵蓋廣泛）：

- **大三和弦**：`C`, `Cmaj`, `CM`, `Cma`
- **小三和弦**：`Cm`, `Cmin`, `Cmi`, `C-`
- **減三和弦**：`Cdim`, `Co`
- **增三和弦**：`Caug`, `C+`
- **六和弦**：`C6`, `Cmaj6`, `CM6`, `C69`, `C6/9`
- **屬七與延伸**：`C7`, `C9`, `C11`, `C13`；變化 9 音如 `C7b9`, `C7#9`
- **大七和弦**：`Cmaj7`, `CΔ7`, `CΔ`, `CM7`
- **小七與延伸**：`Cm7`, `Cmin7`, `C-7`, `Cm9`, `Cm11`, `Cm13`
- **半減七**：`Cm7b5`, `Cø7`, `Cø`
- **減七**：`Cdim7`, `Co7`
- **掛留**：`Csus2`, `Csus4`, `Csus`, `C7sus4`
- **加音**：`Cadd2`, `Cadd9`, `Cadd4`, `Cadd11`, `Cadd6`

多數延伸和弦（9、11、13 等）會包含根音、三音（或掛留音）、五音、七音及標示的延伸音高；程式在給定聲部音域內選擇排列。

**轉位／斜線和弦**

- 可用斜線指定低音：`C/E`, `C/G`, `Am/C`, `D7/F#`, `G/B` 等。
- 生成器會盡量讓**最低聲部符合斜線低音**。

### 和聲如何生成

簡要說明：

- 每個和弦符號會轉成音高集合。
- 對每個和弦產生多個候選排列（密集或稍開放位置），在合理音域內（4–6 聲部）。
- 用基本聲部進行與對位式規則計算從**上一個和弦排列**到每個候選的**成本**；以動態規劃（類 Viterbi）選出總成本最低的路徑。

#### 聲部進行規則（成本在 `harmony.py`）

| 規則 | 效果 |
|------|------|
| **級進** | 偏好 1–2 半音的小步進；大跳懲罰。 |
| **平行五度、八度** | 任兩聲部平行五度或八度（或同度）施以強懲罰。 |
| **隱伏五度／八度** | 低音與高音同向進行到五度或八度時懲罰。 |
| **聲部交叉** | 兩聲部在兩和弦間互換高低順序時懲罰。 |
| **反向進行** | 外聲部（低音與高音）反向進行給予小額獎勵。 |
| **排列** | 和弦過緊或過寬、相鄰聲部間隔超過八度會懲罰。 |
| **重複音** | 排列時非根音最多各一、根音最多二；三音重複會懲罰。 |
| **省略** | 和弦音多於聲部數時（如 G9 四部），**先省略五音**，再依序省略 9、11、13，以保留根、三、七（及盡量保留九音）。 |

傾向音解決（如 V7 的七音下行、導音上行）與特定風格的重複偏好未完整建模。

**調整權重與音域**：在網頁介面中展開「Weights & ranges」可修改聲部進行成本與音域（如平行五八度懲罰、級進偏好、最低／最高音、最大和弦跨度），無需改程式碼。

---

## English

This is a small Python application that:

- **Takes a chord progression as text input**
- **Generates 4-part (or more-part) harmony** that
  - respects the requested chords
  - keeps each voice in a comfortable range
  - prefers stepwise motion
  - avoids large leaps and voice crossings
  - penalizes parallel 5ths/8ves (basic classical-style voice-leading)

The core logic is in `harmony.py` and uses a simple search that chooses, for each chord, the voicing that minimizes a voice-leading cost from the previous chord.

> This is **not** a complete chorale-style engine, but a practical starting point that you can tune and extend.

## Quick start (no programming needed)

**On Windows**, if you **don’t use the command line and don’t know what Bash or coding is**, you can run everything by double‑clicking:

1. **First time only: one-time setup**
   - Open the program folder `chord-harmony-generator` in File Explorer.
   - Find **`setup_harmony_app.bat`** and **double‑click** it.
   - A black window will open and install the required files. **Wait until it finishes** (you’ll see it complete or the window close). You only need to do this once.

2. **Every time you want to use the app**
   - In the same folder, find **`launch_harmony_web.bat`** and **double‑click** it.
   - Your browser should open automatically to the harmony generator page. If it doesn’t, open your browser yourself and go to: **`http://127.0.0.1:5001/`**

3. **On the web page**
   - Type your chord progression in the text box (e.g. `C | F | G7 | C`), choose the number of voices, and click **Generate Harmony**. You’ll see the voices and piano roll and can download the MIDI.

You don’t need to install Python or type any commands—just double‑click the files and use the browser. (On Mac or Linux, use the **Installation** and **Web UI Usage** steps below with the terminal.)

## Installation (with helper script)

From `chord-harmony-generator`, you can use the provided Windows setup script:

```bash
setup_harmony_app.bat
```

This will:

- create a virtual environment in `.venv` (if it does not exist)
- activate it
- install required Python packages from `requirements.txt`

If you prefer to do it manually:

```bash
cd chord-harmony-generator
python -m venv .venv
.\.venv\Scripts\activate  # on Windows
```

Then install dependencies:

```bash
pip install -r requirements.txt
```

## CLI Usage

Run the CLI:

```bash
python main.py
```

You will be prompted for:

- **Number of voices** (e.g. `4` for SATB)
- **Chord progression**, e.g.:

```text
Cmaj | Fmaj | G7 | Cmaj
```

or:

```text
Am | Dm | G | C
```

The program prints a simple text representation of each voice over the progression. If `music21` is installed (from `requirements.txt`), it can also write a MIDI file named `output.mid` in the same folder.

## Web UI Usage

There is also a small web interface built with Flask.

1. Ensure the environment is set up (run `setup_harmony_app.bat` once).
2. Launch the web UI:

```bash
launch_harmony_web.bat
```

3. Open your browser and go to `http://127.0.0.1:5001/` if it does not open automatically.

You will see:

- **Number of voices** input (4–6)
- **Chord progression** text area
- A **Generate Harmony** button that computes and displays:
  - the chord sequence
  - each voice (highest to lowest) as note names in a table
- If `music21` is available, a **Download MIDI** link for `output.mid`.

### Lock and What-if (voicing control)

After generating, each chord column has:

- **Lock** – Check to keep that chord's current voicing fixed. Click **Generate** again to re-optimize the rest of the progression around the locked chord(s). Useful when you've decided one or more chords and want the rest filled in.
- **What if** – Expand to see other good voicings for that chord (scored by local voice-leading cost). Click **Use this** on an alternative to lock that voicing for that chord and re-run the optimizer in one step.

## Chord notation

**Roots** (case-insensitive, with sharps/flats):

`C C# Db D D# Eb E F F# Gb G G# Ab A A# Bb B`

**Common qualities / symbols supported** (not exhaustive, but broad):

- **Major triad**: `C`, `Cmaj`, `CM`, `Cma`
- **Minor triad**: `Cm`, `Cmin`, `Cmi`, `C-`
- **Diminished triad**: `Cdim`, `Co`
- **Augmented triad**: `Caug`, `C+`
- **6 chords**: `C6`, `Cmaj6`, `CM6`, `C69`, `C6/9`
- **Dominant 7th and extensions**:
  - `C7`, `C9`, `C11`, `C13`
  - basic altered 9ths like `C7b9`, `C7#9`
- **Major 7th**: `Cmaj7`, `CΔ7`, `CΔ`, `CM7`
- **Minor 7th and extensions**: `Cm7`, `Cmin7`, `C-7`, `Cm9`, `Cm11`, `Cm13`
- **Half-diminished**: `Cm7b5`, `Cø7`, `Cø`
- **Fully diminished 7th**: `Cdim7`, `Co7`
- **Suspended chords**: `Csus2`, `Csus4`, `Csus`, `C7sus4`
- **Add chords**: `Cadd2`, `Cadd9`, `Cadd4`, `Cadd11`, `Cadd6`

For most extended chords (9, 11, 13, etc.) the app includes the root, 3rd (or suspended tone), 5th, 7th, and the named extensions as pitch classes. It then chooses voicings that fit within the given voice ranges.

**Inversions / slash chords**

- You can specify an explicit bass note using a slash:
  - `C/E`, `C/G`, `Am/C`, `D7/F#`, `G/B`, etc.
- The harmony generator will ensure the **lowest voice matches the slash bass** when possible.

## How the harmony is generated

Very briefly:

- Each chord symbol is converted into a set of pitch classes.
- For each chord, we generate many candidate voicings in closed or slightly open position, in reasonable ranges (for 4–6 voices).
- We compute a **cost** from the previous chord's voicing to each candidate using basic voice-leading and counterpoint-style rules; the path with the lowest total cost is chosen (dynamic programming / Viterbi-style).

### Voice-leading rules (costs in `harmony.py`)

| Rule | Effect |
|------|--------|
| **Stepwise motion** | Small steps (1–2 semitones) preferred; large leaps penalized. |
| **Parallel 5ths and octaves** | Any two voices moving in parallel P5 or P8 (or unison) get a strong penalty (all voice pairs checked). |
| **Direct (hidden) 5ths/8ves** | Bass and soprano moving in the same direction into a P5 or P8 are penalized. |
| **Voice crossing** | Two voices swapping order between chords (e.g. alto drops below tenor) is penalized. |
| **Contrary motion** | Outer voices (bass and soprano) moving in opposite directions get a small bonus. |
| **Spacing** | Very tight or very wide chord spread, and gaps > octave between adjacent voices, are penalized. |
| **Doubling** | Voicing generator allows at most one of each non-root chord tone and at most two roots; doubling the 3rd in triads is penalized. |
| **Omission** | When there are more chord tones than voices (e.g. G9 with 4 voices), the **5th is omitted first**, then 9th, 11th, 13th, so that root, 3rd, and 7th (and 9th when possible) are kept. |

Tendency-tone resolution (e.g. 7th of V7 resolving down, leading tone up) and style-specific doubling (e.g. prefer doubling root/5th over 3rd) are not modeled.

**Adjusting weights and ranges:** In the web UI, open the **"Weights & ranges"** section to change voice-leading costs and pitch range (e.g. parallel 5ths/8ves penalty, stepwise preference, range low/high, max chord spread) without editing code. On first load the form shows defaults; after generating, it shows the values that were used.
