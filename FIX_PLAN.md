# FIX_PLAN — ComfyUI-ControlFoley 修复清单

基线 commit:`6fadc6c`。分支:`fix/ui-preview-and-auto-source`。
执行顺序:任务二 → 任务一 → 任务三 → 任务四(README 必须等代码行为定稿后核对)。
每条一个 commit,commit 后做一轮独立复审,结论追加到对应条目下。
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
- **修法**(节点侧,不动上游;**实测后改判,比原定量化方案更本质**):运行时用旧素材(240 帧 @29.97fps,容器时长 8.008s、最后一帧时间戳 7.9746s)精确复现了 `8.00 < 8.01` 成对两次——两次分别来自 generate(`load_all_frames=False`)与 mux(`load_all_frames=True`)各一次 `load_video`,**不是** root logger 双 handler(否则同一条会连续重复而非成对交替)。根因是容器元数据天然比可解码内容多出约一帧。因此改为:`_media_duration` 优先返回视频流可解码跨度 `(frames-1)/average_rate`(帧数/帧率不可得时回退容器时长);native VIDEO 与 IMAGE 输入路径同样改用落盘后文件的 `_media_duration`。帧数学验证:请求时长 ≤ 最后一帧时间戳时,clip/visual/sync 三路抽帧数均满足 `floor(t*fps)+1` ≥ `t*fps`,告警不可能触发;原量化方案对 25fps sync 流反而除不尽、无法根治。单元实测:8.008s 容器 → 7.9746,6.064s 容器 → 6.05605。
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

### F3.11 无 Triton 平台上 torch.compile 惰性埋雷 + 缓存污染(回归中新发现,计划外新增)
- **问题**:出厂模板回归发现 06_advanced_chain 失败:`Torch Compile` 节点 `compile_encoders=True` 调用 `feature_utils.compile()`,Windows 无 Triton 时 `torch.compile` 惰性编译在首次 `encode_text` 才抛 `TritonMissing`;且编译是对 `_MODEL_CACHE` 共享 runtime 的原地修改,07_simple_generate(compile=false、命中同一缓存)也随之失败。
- **修法**:新增 `_torch_compile_available()`(`torch.utils._triton.has_triton` 优先,回退 `import triton`);TorchCompile 节点与 Model Loader 的 compile_encoders 路径在不可用时跳过并打印说明。有 Triton 的平台行为不变。
- **验证**:修复后 06 success(63.7s,日志出现 skip 说明)、07 不再被污染。

### F3.12 Unload 节点不真正释放显存,反复加载卸载导致显存累积(回归中新发现,计划外新增)
- **问题**:出厂顺序 05→06→07(05/06 各带 Unload 节点)实测:Unload 只 pop `_MODEL_CACHE`,runtime 对象仍被 ComfyUI 执行器输出缓存引用,VRAM 未释放;07 全量重载出第二份模型 → VRAM 溢出到 CUDA sysmem fallback,单次运行从 ~8s 恶化到 800s。这正是审计方向"显存与模型卸载"预判的问题。
- **修法**:(a) Unload 调用 `runtime.unload()`(net/feature_utils 置 None)真正释放张量;(b) 全局 `_UNLOAD_EPOCH` 由 Unload 递增,Loader 的 `IS_CHANGED` 返回该纪元,任何 unload 后强制重载,杜绝执行器把被掏空的 runtime 喂给下游;(c) Generate 对 `net is None` 给出可读报错兜底。
- **验证**:见回归表 round 3。

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

README 改动同样一条一 commit、同样过复审。

---

## 回归要求(全部改完后)

- 七个模板出厂状态直接 Run,记录跑通与耗时(基线:01 修复前 81.01s 含首次加载,纯推理约 30s);零 `ModuleNotFoundError`。
- 任务一:逐模板记录画布上出现的播放器(截图/文字)。
- 任务二:含"源码不在场"四用例。
- is_file、staged_offload=false 两个专项用例结果。
- 结果表追加在本文件末尾。

---

## 最终回归结果(全部修复落地后,重启实跑)

方法:无头启动 ComfyUI(与 Desktop 相同 base 目录与 venv),七个模板出厂状态零改动、同一进程依次运行;画布验收通过浏览器驱动前端排队实跑 + DOM 检查。

| 模板 | 结果 | 耗时(s) | 说明 |
| --- | --- | --- | --- |
| 01_v2a_basic | 通过 | 80.73 | 首个运行,含模型冷加载(修复前基线 81.01) |
| 02_tcv2a_text_controlled | 通过 | 10.72 | 热载 |
| 03_acv2a_audio_controlled | 通过 | 10.42 | 热载;AC-V2A bf16 timbre 路径正常 |
| 04_tv2a_text_video | 通过 | 12.49 | 热载 |
| 05_t2a_basic | 通过 | 7.81 | 热载;末尾 Unload 生效 |
| 06_advanced_chain | 通过 | 53.82 | Unload 后重载;无 Triton 平台打印 compile 跳过说明 |
| 07_simple_generate | 通过 | 52.14 | Unload 后重载;修复 F3.12 前此位置曾恶化到 800s |

- 全程零 `ModuleNotFoundError`;日志零 "video is too short" / "Truncating" 告警。
- 画布证据(浏览器排队实跑 + DOM):Loader 节点 `video-preview` widget + `<video>` readyState=4(temp 副本经 `/view` 200);Muxer 节点 `video-preview` widget(输出 mp4 经 `/view` 200);Save Audio 节点 `audioUI` widget + `<audio>` src 指向输出 wav、readyState=4。三类预览均实证渲染;`app.nodeOutputs` 中三节点 ui 契约与本体一致。
- 任务二"源码不在场"端到端:改名藏起源码 → 重启 → 首次运行自动从 GitHub 浅克隆 pin `6858cd1` → 完整生成保存,67.28s;另有 file:// 机制五用例、坏 URL、目标不完整、开关关闭四类用例全过。
- 专项:is_file 两例报可读 ValueError;staged_offload=false 跑通(28.9s);采样中段取消 0.96s 中断(每 4 步同步,吞吐损耗 ~2%);`HF_HUB_OFFLINE=1` + 完整缓存加载正常。

---

## 附录 A:给上游的 PR 描述草稿(audio_model.py timbre dtype)

> **Fix dtype mismatch for timbre features in `preprocess_conditions`**
>
> In `controlfoley/audio_model.py`, `preprocess_conditions` projects four feature streams symmetrically (`sync_input_proj` / `text_input_proj` / `clap_input_proj` / `timbre_input_proj`). The first three receive features that are already in the network's compute dtype, but `timbre_f` arrives as `float32` because the timbre extraction path (`encode_audio_with_music_model` → `timbre_feature.float()` in `inference_utils.generate`) explicitly casts to float32. When the model runs in `bf16`/`fp16`, `timbre_f = self.timbre_input_proj(timbre_f)` (around L728) then fails with a dtype-mismatch matmul error.
>
> Proposed fix: align dtype/device at the top of `preprocess_conditions`, e.g. `timbre_f = timbre_f.to(dtype=self.timbre_input_proj.weight.dtype, device=self.timbre_input_proj.weight.device)` — or drop the `.float()` cast in `inference_utils.generate`. Downstream integrations currently have to monkeypatch `preprocess_conditions` to work around this.

---

## 复审记录

### F0(57c652f)
- 复审指出:auto-fetch 若只是 clone 到固定目标、调用方仍沿用先前解析出的(可能错误的)`source_dir`,首次运行仍会检查错目录。**接受**——F2.1 实现改为:helper 成功时返回最终目录,调用方用返回值覆盖 `source_dir`;并明确 auto-fetch 只落到默认根目录位置,不 clone 到用户显式路径。
- `.gitignore` 改动无缺陷。

### F1.1(8d07834)/F1.2(5848931)/F1.3(5bd59c0)
- 复审三条均未发现实际缺陷;F1.1 并对照上游 `PreviewVideo.as_dict()` 契约核对一致。

### F1.4(44eb13a)
- 复审报 7 条 "widgets_values 里 'fixed' 后多了 '25'"。**全部拒绝**:`seed` 是 INT widget,前端为其附加 `control_after_generate` widget 且序列化在 seed 值之后,`[42, "fixed", "25", 4.5]` 依次是 seed / control_after_generate / num_inference_steps / guidance_scale;README 明确记载"control_after_generate 设为 fixed、steps 设为 25",且这批模板两轮验收均按预期参数跑通,若真错位布尔字段早已崩溃。复审漏算了附加 widget。

### F1.5(a9884a1)
- 复审未发现实际缺陷;确认 optional 位置不打乱旧 workflow widgets_values 对位。
- 实测:重启后 SaveAudio 节点出现 `audioUI` widget,运行后 `<audio>` 元素 src 指向 `/view?...wav`、readyState=4 可播放。

### F3.3(c662cbd + F3.3b 加固)
- 复审两条:(1) VFR 下 `(frames-1)/average_rate` 非精确——**部分接受**:加 `min(候选值, 容器时长)` 钳制防过冲;完整解码求末帧 PTS 的方案**拒绝**(loader 路径上解码整只视频代价过高,VFR 残余误差的后果只是原有告警偶发出现,非新回归);(2) 音频将比视频短约一帧——**接受为有意取舍**:修复前上游同样会把生成截断到帧网格,实际输出时长差 8-40ms,换取结构性告警根治;不为此增加"抽帧时长/输出时长"双管道。
### F2.1(8456f9b + F2.1b e87e892)
- 实测记录:本地 file:// 镜像五用例全 PASS(clone 成功/幂等/坏 URL 干净失败无残留/目标存在但不完整时拒绝且不动用户目录/开关关不 clone);本机 GitHub 直连可达,上游 HEAD 即 pin 的 `6858cd1`。
- 复审指出:并发保护仅进程内 Lock,两个共享同一 ComfyUI 根目录的进程同时 fetch 时,后完成者 rename 失败会误报失败。**部分接受**——在失败路径复查目标目录是否已被他人落地完整,是则直接采用(F2.1b 修入);**拒绝**跨进程锁文件方案:双进程共根目录本身是罕见部署,复查已覆盖其后果,锁文件反而引入陈旧锁清理问题。
- 端到端实测(源码不在场 + 真实 GitHub):重启后首次运行自动浅克隆 `6858cd1` 到 `<ComfyUI>/controlfoley`,随后完整走完 T2A 生成并保存 wav,全链 67.28s;clone 后 `git rev-parse HEAD` 与 pin 完全一致。

### F3.7(6fe6091)
- 复审未发现实际缺陷;确认存取 key 统一后不会跨 load_all_frames 维度误命中。实测:同参数二次运行 1.31s(首轮 77.46s),mux 特征缓存命中。

### F3.1(1a419e4 + F3.1b 428fca9)
- 复审指出 `local_files_only=True` 命中不等于缓存完整,本地优先会让在线用户的残缺缓存失去自动补全。**接受**,但用更简单的等价方案落地:改为网络优先(保留原有补全语义)、网络异常回退本地缓存、双失败才抛带 `HF_ENDPOINT` 镜像指引的错误。`HF_HUB_OFFLINE=1` + 完整缓存实测通过。F3.1b 复审无缺陷。

### F3.2(ece91a0)
- 复审未发现实际缺陷,并确认:adaptive 模式同样经过包装;`InterruptProcessingException` 继承 `BaseException`,不会被 Advanced 节点的 `except Exception`(silent_audio_on_error)吞掉;torch.compile 只编译 net,不涉及此闭包。

### F3.4(66a22a1)
- 单测:位置/关键字两种传法均对齐 dtype、上游新增第 7 参可转发、None 安全、定位失败打 WARNING。复审未发现实际缺陷。

### F3.5(8c2818d)
- 复审未发现实际缺陷;进程内一次性提示,tooltip 不影响 widgets_values 对位。

### F3.6(49e1ac8 + F3.6b 9e97272)
- 运行时实证:`/workflow_templates` 恰好 7 条、仅注册 `example_workflows/`,旧目录属纯冗余(非重复注册)。复审确认仓库内无代码引用断链,文档引用由任务四处理;`.gitignore` 过期例外行在 F3.6b 同步修正。

### F3.8(755900e)/F3.9(068445b)
- 复审均未发现实际缺陷。F3.9 实测:60h 旧文件启动即清、新文件保留(经 folder_paths shim 在真实 output 目录验证)。

### F4.R1(b31ec82 + R1b 9546293)
- 复审指出 Demo Workflows 段仍写"运行前必须手动备好源码树",与新行为不一致——**接受**,R1b 修正。其余描述与实现核对一致。

### F4.R2(7078728)/F4.R3(ea03c12)/F4.R4(4638b8c)/F4.R9(9b28507)
- 直接落地。R4 后用 grep 复核仓库内不再有 `examples/workflows` 活引用;R3 权重体量按实测 16 GB(核心 11 GB + 外部 5 GB)写入;R11 四个外链实测均 200。

### F3.11(03b4f05)
- 复审未发现实际缺陷,确认两个原地编译入口均已守卫、有 Triton 平台行为不变。

### F3.12(8a0e8d1 + F3.12b bc83a38)
- 复审两条:(1) `key in _MODEL_CACHE` token 在 unload→rerun→unload 循环下值不变会漏跑;(2) IS_CHANGED 中连接输入(dependencies)传入为 None,按 widget 算 key 会算错。**均接受**——F3.12b 改为全局 `_UNLOAD_EPOCH` 方案,不再在 IS_CHANGED 里算 key。
- F3.12b 复审指出全局纪元粒度粗,任一 unload 会让所有 Loader 变脏、独立分支的下游生成被连带重跑。**接受为已知残留、不改**:per-model 精确失效需要在 IS_CHANGED 里算 key,而连接输入不可用(即第 2 条否掉的路);粗粒度多付的是多模型并存工作流的重复计算,换来"绝不把已卸载模型喂给下游"的安全性;出厂 7 模板均为单模型链,不受影响。已列入 PR"已知残留"。

### F4.R5(7a3885e + R5b 65792e0)
- 复审指出 Known Issues 段还有一句未加限定——**接受**,R5b 修正。其余段落与 `supports_staged_offload` 探测逻辑核对一致。
