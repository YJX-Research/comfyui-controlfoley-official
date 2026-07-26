# FIX_PLAN — ComfyUI-ControlFoley 修复清单

基线 commit:`6fadc6c`。分支:`fix/ui-preview-and-auto-source`。
执行顺序:任务二 → 任务一 → 任务三 → 任务四(README 必须等代码行为定稿后核对)。
每条一个 commit,commit 后跑 `codex exec` review,结论追加到对应条目下。
路径写法约定:`<ComfyUI>` = ComfyUI 根目录,`<node>` = 本节点包目录,`<upstream>` = 上游 controlfoley 源码目录。

---

## 前置

### F0. 分支与仓库卫生
- **问题**:`.gitignore` 未排除 review 中间产物;FIX_PLAN 需要入库。
- **修法**:建分支;提交本文件;`.gitignore` 追加 `.review/` 与 `.pr_body.md`。
- **验证**:`git status` 干净;diff 文件不入库。
- **风险**:无。

---

## 任务二:自动获取上游源码(先做)

### F2.1 实现 `auto_fetch_source`(git 自动 clone,pin revision,原子落地)
- **问题**:`_ensure_public_controlfoley_repo`(nodes.py:418-436)只有 `exists()` 检查,失败直接 `raise FileNotFoundError`,无任何下载逻辑;全文件 grep `subprocess|git` 为空。自动探测链(nodes.py:129-145)已可用,缺的只是"下载"这一段。
- **证据**:nodes.py:418-436;nodes.py:129-145。
- **修法**:
  - 模块级常量:`CONTROLFOLEY_SOURCE_REPO_URL`(默认 GitHub 上游地址,可被环境变量 `CONTROLFOLEY_SOURCE_URL` 覆盖)、`CONTROLFOLEY_SOURCE_PIN = "6858cd12a48d141201e3266e7abe1f38357a133e"`(与本地实测可用的上游 HEAD 一致;pin 的原因:现有代码完全不校验上游版本,上游改 API 会直接炸,注释写明)。
  - 新函数 `_auto_fetch_controlfoley_source()`:目标位置固定为 `<ComfyUI>/controlfoley`(自动探测链已覆盖该位置;明确不放节点包内部、不放 custom_nodes 下)。
  - 实现:`subprocess.run` list argv、`shell=False`、每步带 timeout;浅克隆 + pin 用 `git init` → `git remote add` → `git fetch --depth 1 origin <pin>` → `git checkout FETCH_HEAD` 序列;先落到同盘临时目录(`<ComfyUI>/controlfoley.tmp-<pid>` 一类),全部成功后 `os.replace`/rename 到最终位置;任何一步失败删除半成品目录。
  - 并发/重入:模块级 `threading.Lock` + rename 的原子性双保险。
  - 显式可控:三个入口节点(Dependencies Loader / Model Loader / Simple Generate)加布尔 widget `auto_fetch_source`,描述写明会执行 git clone、目标位置;widget **追加在 required 末尾**,避免打乱旧 workflow 按下标存的 widgets_values。
  - 日志:clone 前打印仓库地址 + 目标位置;成功/失败均打印。
  - 失败回退:任何失败(含超时)回落到现有那条报错文案(缺失文件列表 + 手动 clone 指引),并在文案中追加 `CONTROLFOLEY_SOURCE_URL` 环境变量的用法提示,不用 `download failed` 一句话盖掉。
  - 许可:只 clone Apache 2.0 的源码;权重下载仍走原有 `auto_download` 开关,两者不合并。
- **影响面**:三个节点 INPUT_TYPES 追加一项;新增一个函数与两个常量;报错文案增强。
- **验证**:四个用例,均需先 `Rename-Item` 把现成源码藏起来:(a) 源码不存在 + 开关开 → 自动 clone 成功、流程跑通;(b) 源码存在但文件不全 → 报可读错误(不误判为就绪);(c) 网络不可达 → 超时后干净回退到手动指引,无半成品目录残留;(d) 开关关 → 行为与现在完全一致。测完恢复原目录。
- **风险**:中。Windows 上 rename 目标已存在会失败(用例覆盖);git 不在 PATH 的机器需回退到手动指引(报错文案覆盖)。

### F2.2 备注:HF 镜像备选方案(不实现,仅记录)
若实测国内 git 直连失败率高到该功能形同没修:备选是把上游源码镜像到 HF 仓库,用已是依赖的 `huggingface_hub.snapshot_download` 拉取(HF 有国内镜像端点 `HF_ENDPOINT`,比 GitHub 稳,且下载器已在依赖里、支持断点续传)。此条留给仓库作者决策,本次不做。

---

## 任务一:可视化预览(视频框 + 音频框)

### F1.1 视频预览 `ui` 键名从 VHS 私有契约改为本体契约
- **问题**:三处 `ui` 返回(Video Loader nodes.py:1051、Save Audio:1278、Muxer:1331)中,视频走 `_video_ui`(nodes.py:766-771),返回 `{"gifs": [...]}`。`"gifs"` 是 Video Helper Suite 扩展的私有键;对当前 ComfyUI Desktop 前端 bundle 全量 grep,`"gifs"` **零命中**——前端根本不消费这个键,这就是"返回了 ui 但画布空白"的根因。本体视频预览契约是 `{"images": [SavedResult...], "animated": (True,)}`(`comfy_api/latest/_ui.py` `PreviewVideo.as_dict`,`SaveVideo`/`SaveWEBM` 实际使用)。音频的 `{"audio": [...]}` 与本体 `SavedAudios.as_dict` 一致,前端有 `audioUI` widget 消费,预期本来就能渲染(运行时确认)。
- **证据**:nodes.py:766-771;ComfyUI `comfy_api/latest/_ui.py:428-433`(PreviewVideo)、`:59-65`(SavedAudios);前端 bundle grep `"gifs"` 零命中、`audioUI` 有命中。
- **修法**:`_video_ui` 返回 `{"images": [entry], "animated": (True,)}`,entry 键 `filename/subfolder/type` 逐字对齐 `SavedResult`;去掉无人消费的 `format` 字段。
- **影响面**:三个输出节点的画布渲染;不改 socket、不改文件落盘。
- **验证**:重启 ComfyUI 实跑,Loader / Muxer 节点上出现视频播放器,Save Audio 出现音频播放器。
- **风险**:低。

### F1.2 预览副本落到 ComfyUI temp 目录而不是 output
- **问题**:`_preview_video_path`(nodes.py:754-763)把 output/input 之外的视频(如随包 demo 素材)整只拷进 `output/controlfoley/previews/`,永久累积、无人清理,且把"预览缓存"混进用户产出目录。本体做法(`PreviewAudio`/`PreviewImage`)是写 `folder_paths.get_temp_directory()`、type 用 `"temp"`,ComfyUI 重启自动清。
- **证据**:nodes.py:754-763;ComfyUI `comfy_api/latest/_ui.py:413-422`。
- **修法**:预览副本写 `folder_paths.get_temp_directory()` 下,`_ui_file_entry` type 传 `"temp"`(相应支持 temp 基准目录);已在 output/input 内的文件维持现状直接引用。
- **影响面**:仅预览路径;输出文件不动。
- **验证**:跑 01 模板,previews 目录不再新增文件;temp 下出现副本且预览可播;重启后自动清理。
- **风险**:低。`/view` 接口原生支持 `type=temp`。

### F1.3 Video Loader 增加原生 `VIDEO` 输出 socket
- **问题**:Loader 已是 `OUTPUT_NODE`(nodes.py:1031),F1.1 后 inline 预览应当直接可见;但其输出是自定义类型 `CONTROLFOLEY_VIDEO`,无法接本体 `SaveVideo`/`Get Video Components` 等原生节点。判断依据:本体这一版没有独立的 `PreviewVideo` 节点(全 comfy_extras 无该 node_id),"接本体 Preview 节点"这条路对视频不存在,所以 inline `ui` 预览(F1.1)是主要交付,`VIDEO` socket 是互操作补充。
- **修法**:RETURN_TYPES 末尾追加 `VIDEO`(`InputImpl.VideoFromFile(path)`,与本体 `LoadVideo` 同实现);追加在末尾不影响既有连线下标。
- **影响面**:Loader 增一路输出;旧 workflow 兼容。
- **验证**:新建图,Loader→SaveVideo 连通且能跑;旧模板加载无报错。
- **风险**:低。`comfy_api.latest.InputImpl` 在本体 `nodes_video.py` 中同样使用,导入失败时降级为不注册该输出(try/except + warning)。

### F1.4 七个模板补齐/摆正预览
- **问题**:预览渲染后 Save Audio / Muxer 节点会变高,现模板 `[1020,120]` 与 `[1020,320]` 纵向间距 200px 会叠;需要逐模板确认"输入视频可预览、输出音频有播放器、有视频输出的有视频播放器"(T2A 只要求音频)。
- **修法**:调整 7 个模板 JSON 的节点位置;01-04 依赖 Loader/SaveAudio/Muxer 自带预览即可,不额外加节点;05-07 依赖 SaveAudio 播放器。若运行时发现某路 inline 预览不成立,再改为显式接预览节点并在此记录。
- **验证**:七个模板逐个出厂状态 Run,截图/描述画布上出现的播放器,不叠框。
- **风险**:低,纯 JSON 摆位。

### F1.5 Save Audio 节点声明 `AUDIO_UI` widget(运行时新发现,计划外新增)
- **问题**:实跑发现返回 `{"audio": [...]}` 后画布上仍无播放器。根因:前端 `Comfy.AudioWidget` 扩展只给硬编码的核心节点类(`LoadAudio/SaveAudio/PreviewAudio/SaveAudioMP3/SaveAudioOpus/SaveAudioAdvanced`)注入 `audioUI` widget;`onNodeOutputsUpdated` 只**更新已存在**的 `audioUI` widget,不会为自定义节点创建。视频的 `images+animated` 路径无此限制(实测 Loader 与 Muxer 预览均已渲染)。
- **证据**:前端 bundle `Comfy.AudioWidget` 扩展源码(beforeRegisterNodeDef 的硬编码类名列表);实跑模板 01:`app.nodeOutputs` 中三个节点结果齐全,仅 SaveAudio 无 widget。
- **修法**:`SaveControlFoleyAudio.INPUT_TYPES` 的 optional 里声明 `"audioUI": ("AUDIO_UI",)`(放 optional 避免"widget 不序列化 → 服务端校验缺必填参数"的风险),`save`/`IS_CHANGED` 加 `audioUI=None` 兼容其序列化与否两种行为。
- **验证**:重启后实跑,SaveAudio 节点出现可播放的音频控件。
- **风险**:低。

---

## 任务三:整体 code review(按严重程度排序)

### F3.1 断网时依赖缓存检查直接炸(即使本地缓存完整)
- **问题**:`_ensure_hf_dependency_cache`(nodes.py:206-216)对每个依赖仓库无条件 `snapshot_download`;无网络时 HF 会抛错 → 包装成 RuntimeError,模型加载失败——哪怕缓存早已完整。离线/弱网用户首次加载必挂。
- **修法**:先 `snapshot_download(..., local_files_only=True)` 探测本地缓存,命中即跳过;未命中再走网络下载,网络失败时报错文案指出可预缓存 + `HF_ENDPOINT` 镜像用法。
- **验证**:断网 + 缓存完整 → 加载成功;断网 + 缓存缺失 → 可读报错。
- **风险**:低。

### F3.2 取消(cancel)在长推理中无响应
- **问题**:采样期间点 cancel 无法中断。上游 `lib/flow_matching.py:58-72` 的 euler 循环逐步调用 `fn(t, x)`,无任何中断检查;节点侧把 `FlowMatching` 原样实例化(nodes.py:1180)。ComfyUI 提供 `comfy.model_management.throw_exception_if_processing_interrupted()`(model_management.py:2032)。
- **修法**:节点侧包装:实例化 fm 后,把传入 `generate` 的采样函数路径包一层——具体做法是子类化/包装 `FlowMatching.run_t0_to_t1`,在每步回调里先调 `throw_exception_if_processing_interrupted()` 再调原 `fn`。不改上游文件。编码器/vocoder 阶段仍不可中断(上游内部),在 FIX_PLAN 残留区注明。
- **验证**:发起 25 步生成,中途 cancel,数秒内中断且下一次运行正常。
- **风险**:低。仅影响采样循环,数值路径不变。

### F3.3 "video is too short" 告警(含自比较样式)与重复打印
- **问题**:上游 `load_video`(inference_utils.py:216-226)把"抽到的帧数/fps"与请求时长比较,而节点把未量化的容器时长直接传入(loader:nodes.py:1048-1049;mux:1315-1318)。容器元数据时长几乎从不落在 1/8s(clip)、1/4s(visual)、1/25s(sync)帧网格上,所以只要素材时长不是整帧数,告警必然出现;显示保留两位小数还会出现 `7.96 < 7.96` 这种"自己和自己比"的样式(实际是 7.9583 < 7.96)。实测随包 `v2a_video.mp4` 容器时长 6.064s(非整数帧网格),复现条件成立。重复打印的两个候选根因:(a) generate 路径(`load_all_frames=False`)与 mux 路径(`load_all_frames=True`)各 load 一次,缓存 key 含 `load_all_frames` 必然二次加载;(b) 上游 `log = logging.getLogger()` 是 root logger,宿主 root logger 若挂了多个 handler 会逐条翻倍。两者在运行时用日志标记区分确认。
- **修法**(节点侧,不动上游):把传给 `load_video` 的请求时长向下量化到 1/`_CLIP_FPS`(0.125s)网格(loader 的 `effective_duration`、generate 的 `requested_duration`、mux 的 `duration` 三处统一);mux 传入的时长改用生成阶段截断后的实际时长(min 逻辑保留)。量化后元数据舍入类告警消失;若素材内容真短于元数据超过一帧,告警保留——那是真实问题,应当让用户看到。重复打印若确认是 root logger 双 handler,则属宿主环境问题,记录残留不修;若是二次 load,量化后 mux 一侧的告警同样消失。
- **验证**:01-04 模板出厂 Run,控制台零 "too short" 告警;人为喂一个内容确实偏短的视频,告警只按真实差距出现。
- **风险**:低。量化最多截掉 0.125s 内容,远小于现在被上游随手截断的量。

### F3.4 timbre dtype monkeypatch 的两处脆弱性
- **问题**:`_patch_timbre_dtype_alignment`(nodes.py:439-457):(a) `getattr` 拿不到 `preprocess_conditions`/`timbre_input_proj` 时静默 return,上游重命名后 bf16 崩溃会无声回归;(b) `_patched_preprocess_conditions` 写死六个位置参数,上游加参数直接 TypeError。
- **修法**:(a) 定位失败改为 `print("[ControlFoley] WARNING: ...")` 明确说 patch 未生效及后果;(b) 签名改 `*args, **kwargs`,按位置/关键字定位 `timbre_f`(最后一个位置参数或 kwargs),转换后原样转发。
- **验证**:正常路径 bf16 AC-V2A 跑通;临时把属性改名模拟上游重构,确认打出 warning 而非静默。
- **风险**:低。

### F3.5 `staged_offload` 对 pin 的公共源码是静默 no-op
- **问题**:上游 `generate()`(inference_utils.py:38-55)签名只有 `clip/sync_batch_size_multiplier` 和 `image_input`,**没有** `staged_offload`,也没有 `**kwargs`(上游全仓 grep `staged_offload` 零命中)。节点的能力探测(nodes.py:1190-1196)会正确地不传它——但用户把开关设为 True 时没有任何提示,README 还宣称它"将编码器移到 CPU"(README.md:269)。这同时覆盖已知问题 7("false 路径没测过"):对公共源码,true/false 行为本就相同。
- **修法**:能力探测发现源不支持而用户开了开关时,打一条 console 提示("当前源码不支持 staged_offload,已忽略");tooltip 补充说明。README 措辞修正归任务四。
- **验证**:staged_offload=true/false 各跑一次 01 模板,均出提示/均跑通,耗时与 VRAM 相近。
- **风险**:低。

### F3.6 `examples/workflows/` 与 `example_workflows/` 完全重复
- **问题**:7 个 JSON 两份逐字节相同(cmp 实测 IDENTICAL)。ComfyUI 只扫 `example_workflows/`,旧目录是死重量、日后必不同步;README 还在引导用户去 `examples/workflows` 手动加载(README.md:75、128-135)。
- **修法**:`git rm examples/workflows/`;README 引用改为 `example_workflows/`(归任务四条目执行)。运行时确认 Browse Templates 恰为 7 条(若是 14 条则说明旧目录也被注册,一并在验证记录中写明)。
- **验证**:Browse Templates 数量与打开正常。
- **风险**:低。直接从 GitHub clone 老仓库的用户不受影响(模板仍在 example_workflows)。

### F3.7 视频特征缓存 key 不一致,截断场景永不命中
- **问题**:`_get_cached_video` 用**请求时长**查(nodes.py:1156),`_cache_video` 用 `video_info.total_duration`(截断后)存(nodes.py:516)。一旦上游截断(即 F3.3 场景),存取 key 不同,缓存形同虚设,每次 Run 重复抽帧。
- **修法**:`_cache_video` 增加"请求时长"参数,存取用同一个 key;F3.3 的量化落地后二者通常相等,此条是兜底。
- **验证**:同一模板连续 Run 两次,第二次日志无重复 load_video。
- **风险**:低。

### F3.8 静默吞异常处补日志
- **问题**:`_media_duration`(nodes.py:296-298)、`_device_from_choice`(:396-397)、`_free_vram_for_low_vram_load`(:411-412)、`_patch_bigvgan_from_pretrained`(:544-545)吞掉异常不留痕,排障时无从下手。
- **修法**:各处加一行 `print("[ControlFoley] ...")` 级别的说明(含异常摘要),行为不变。`_comfy_video_duration`(:274-275)返回 None 属正常协议,不动。
- **验证**:正常运行无新增噪音;人为制造坏文件确认有日志。
- **风险**:无。

### F3.9 `output/controlfoley/temp` 中间文件无人清理
- **问题**:`_temp_video_path`(nodes.py:83-84)为 VIDEO/IMAGE 输入生成的临时 mp4 累积不清理;生成期间及 mux 阶段仍要引用同一路径,不能即用即删。
- **修法**:模块加载时清理该目录下超过 48h 的旧文件(启动时一次,异常吞掉但打日志)。保守方案,避免删到当前 run 正在用的文件。
- **验证**:放入旧文件,重启后被清;当前 run 的临时文件不受影响。
- **风险**:低。

### F3.10 版本号 bump 0.1.1 → 0.1.2
- **问题**:Registry 0.1.1 为 Pending;本批改动 merge 后需以 0.1.2 重新 publish。
- **修法**:`pyproject.toml` version 改 0.1.2(作为最后一个代码 commit);PR 描述注明"merge 后需重新 publish"。
- **验证**:无。
- **风险**:无。

### 只验证、不改码(或待作者确认)的项
- **is_file() 校验实测**(nodes.py:736、1046-1047):把目录填进 `video_path` / `reference_audio_path`,确认报可读错误而非 `av` 的 PermissionError。结果记入回归表。
- **05/06/07 三个 wav 是同一文件**(SHA256 实测相同,均 `af3d7709...`):按约定**换之前先问仓库作者**,本批不动 `examples/generated/`,列入 PR"已知残留"。
- **上游 `audio_model.py` L728 timbre 投影缺 dtype 转换**:不在本仓库范围。可直接贴给上游的 PR 描述草稿见附录 A。
- **模型不接 ComfyUI model_management 生命周期**:`_MODEL_CACHE` 常驻显存直到手动 Unload,ComfyUI 需要 VRAM 时无法自动逐出。改造涉及把 runtime 包成 `ModelPatcher`,风险大于收益(alpha 阶段),记录为残留;`UnloadControlFoleyModel` 已提供手动出口。
- **线程安全**:`_MODEL_CACHE`/`_VIDEO_CACHE`/patch 标记均为模块级可变状态,但 ComfyUI 执行器单线程调度节点,当前无实际竞态;F2.1 的下载锁除外(已做)。记录不改。
- **路径校验**:`_resolve_path` 接受任意绝对路径,与本体 Load 类节点接受任意路径的行为一致(本地部署信任模型),不加 traversal 限制;`_safe_path` 已对输出前缀做了清洗。记录不改。
- **requirements.txt**:维持 `>=` 范围不动(动版本约束风险高于收益);`spacy` 由上游 MusicGen 依赖链引入,是否需要额外语言模型在回归时观察首个 AC-V2A 运行,如需则仅在 README 注明,不改依赖。**不执行 `pip install -r requirements.txt`**。

---

## 任务四:README 审查(最后做)

先按最终代码行为逐步照做一遍安装/使用流程,产出"README 说的 / 实际是的"对照表,再按表改。已静态确认的不一致(运行时可能再增补):

| # | README 说的 | 实际是的 | 处理 |
| --- | --- | --- | --- |
| R1 | 装完节点后"另外手动 clone 上游源码"(README.md:40、55-59、73) | F2.1 落地后默认可自动获取,手动 clone 变为备选/离线路径 | 改 README:主路径写 `auto_fetch_source`,手动 clone 降为备选,补 `CONTROLFOLEY_SOURCE_URL` 说明 |
| R2 | `pip install -r requirements.txt`(README.md:48、72)无任何风险提示 | `>=` 范围解析可能顶掉环境里的 torch/numpy 生态版本 | 补注:建议在 ComfyUI 自带环境按缺失单装;写明该命令可能变更已装版本 |
| R3 | 权重"自动从 HF 下载"(README.md:82)未写体量、未写国内镜像 | 五个权重文件数 GB 级;无 `HF_ENDPOINT` 时国内表现为"卡住不动"而非报错 | 补:权重大致体量、下载目录、`HF_ENDPOINT=https://hf-mirror.com`(含 PowerShell `$env:` 写法) |
| R4 | "load a workflow from `examples/workflows`"(README.md:75)、Folder Structure 列 `examples/workflows/*.json`(README.md:128-135) | F3.6 删除后该目录不存在;实际扫描目录是 `example_workflows/` | 改 README 两处;Folder Structure 同步补 `example_workflows/`、`examples/generated/`、`model_urls.py` 缺失项 |
| R5 | `staged_offload` "moves encoders to CPU during DiT sampling"(README.md:269、大量默认值表述) | 对 pin 的公共源码是 no-op(F3.5) | 措辞改为"仅在源码支持时生效,当前公共源码不支持、会打提示" |
| R6 | "Output nodes show audio/video previews"(README.md:78) | 修复前视频预览不渲染;修复后成立 | 任务一落地后核对无误则保留 |
| R7 | 素材路径/名称(README.md:222-233 映射表) | 与 `examples/generated/` 实际文件逐个核对(6fadc6c 换过素材;旧名 001-004.mp4/003.wav 已不存在) | 逐项核对,死链就改 |
| R8 | 模板 7 个、名称列表(README.md:157-165) | 与 `example_workflows/` 实际 JSON 逐个核对 | 核对,不一致就改 |
| R9 | 节点名列表(README.md:140-151) | 与 `NODE_DISPLAY_NAME_MAPPINGS`(nodes.py:1374-1385)逐个核对 | 静态初核一致;加入 F1.3 新输出后复核描述 |
| R10 | 许可段(README.md:307-316) | 权重 CC BY-NC 4.0 已写明 ✔ | 核对保留 |
| R11 | GitHub / Registry / HF 链接 | 逐个打开验证 | 运行时验证 |
| R12 | `pyproject.toml` description/version/依赖 vs README/Registry | version 将变 0.1.2;description 与 README 简介核对 | 同步 |

README 改动同样一条一 commit、同样过 Codex review。

---

## 回归要求(全部改完后)

- 七个模板出厂状态直接 Run,记录跑通与耗时(基线:01 修复前 81.01s 含首次加载,纯推理约 30s);零 `ModuleNotFoundError`。
- 任务一:逐模板记录画布上出现的播放器(截图/文字)。
- 任务二:含"源码不在场"四用例。
- is_file、staged_offload=false 两个专项用例结果。
- 结果表追加在本文件末尾。

---

## 附录 A:给上游的 PR 描述草稿(audio_model.py timbre dtype)

> **Fix dtype mismatch for timbre features in `preprocess_conditions`**
>
> In `controlfoley/audio_model.py`, `preprocess_conditions` projects four feature streams symmetrically (`sync_input_proj` / `text_input_proj` / `clap_input_proj` / `timbre_input_proj`). The first three receive features that are already in the network's compute dtype, but `timbre_f` arrives as `float32` because the timbre extraction path (`encode_audio_with_music_model` → `timbre_feature.float()` in `inference_utils.generate`) explicitly casts to float32. When the model runs in `bf16`/`fp16`, `timbre_f = self.timbre_input_proj(timbre_f)` (around L728) then fails with a dtype-mismatch matmul error.
>
> Proposed fix: align dtype/device at the top of `preprocess_conditions`, e.g. `timbre_f = timbre_f.to(dtype=self.timbre_input_proj.weight.dtype, device=self.timbre_input_proj.weight.device)` — or drop the `.float()` cast in `inference_utils.generate`. Downstream integrations currently have to monkeypatch `preprocess_conditions` to work around this.

---

## Codex review 记录

### F0(57c652f)
- Codex 指出:auto-fetch 若只是 clone 到固定目标、调用方仍沿用先前解析出的(可能错误的)`source_dir`,首次运行仍会检查错目录。**接受**——F2.1 实现改为:helper 成功时返回最终目录,调用方用返回值覆盖 `source_dir`;并明确 auto-fetch 只落到默认根目录位置,不 clone 到用户显式路径。
- `.gitignore` 改动无缺陷。

### F1.1(8d07834)/F1.2(5848931)/F1.3(5bd59c0)
- Codex 三条均未发现实际缺陷;F1.1 并对照上游 `PreviewVideo.as_dict()` 契约核对一致。

### F1.4(44eb13a)
- Codex 报 7 条 "widgets_values 里 'fixed' 后多了 '25'"。**全部拒绝**:`seed` 是 INT widget,前端为其附加 `control_after_generate` widget 且序列化在 seed 值之后,`[42, "fixed", "25", 4.5]` 依次是 seed / control_after_generate / num_inference_steps / guidance_scale;README 明确记载"control_after_generate 设为 fixed、steps 设为 25",且这批模板两轮验收均按预期参数跑通,若真错位布尔字段早已崩溃。Codex 漏算了附加 widget。

### F2.1(8456f9b)
- 实测记录:本地 file:// 镜像五用例全 PASS(clone 成功/幂等/坏 URL 干净失败无残留/目标存在但不完整时拒绝且不动用户目录/开关关不 clone);本机 GitHub 直连可达,上游 HEAD 即 pin 的 `6858cd1`。
- Codex 指出:并发保护仅进程内 Lock,两个共享同一 ComfyUI 根目录的进程同时 fetch 时,后完成者 rename 失败会误报失败。**部分接受**——在失败路径复查目标目录是否已被他人落地完整,是则直接采用(F2.1b 修入);**拒绝**跨进程锁文件方案:双进程共根目录本身是罕见部署,复查已覆盖其后果,锁文件反而引入陈旧锁清理问题。
