# UBLink-DT — Unified Bus Link Diagnostic Tool

UBLink-DT 是灵衢协议（Unified Bus）链路诊断工具集，命令入口为 `ublinkdt`，通过 `-m` 参数选择诊断模块。

当前支持的模块：

| 模块 | 说明 | 文档 |
| --- | --- | --- |
| `otpd` | 光模块脏污检测 | [docs/zh/otpd/README.md](docs/zh/otpd/README.md) |

## 快速开始

需要 Python 3.7 或更高版本。交付模式运行时仅依赖 Python 标准库，不需要安装第三方运行库。

```bash
python -m pip install -e .
ublinkdt -h
```

如果帮助信息可以正常显示，说明 CLI 入口已经安装成功。模块使用方法见对应模块文档。

详见 [otpd 模块文档](docs/zh/otpd/README.md)。

## 安装模式

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 交付/运行 | `python -m pip install -e .` | 不安装测试依赖；`install_requires=[]` |
| 构建 wheel | `python -m pip install -r requirements.txt` | 只安装 `build`、`setuptools`、`wheel` |
| Debug 运行 | 见“Debug 运行” | 构建并安装会响应 `OTPD_STUB_MODE` 的 Debug wheel |

`requirements.txt` 只用于构建工具依赖，不包含 `pytest`。测试依赖需要在开发环境中单独安装。内网交付环境如果只安装交付包，不会触发测试依赖安装。

## 构建 Wheel

构建交付 wheel：

```bash
python -m pip install -r requirements.txt
python -m build --wheel --no-isolation
python -m pip install dist/ublinkdt-1.0.0-py3-none-any.whl
```

构建 Debug wheel：

```bash
python -m pip install -r requirements.txt
python -m build --wheel --no-isolation -C--build-option=--debug-build
python -m pip install dist/ublinkdt-1.0.0-py3-none-any.whl
```

Debug wheel 会在构建产物中写入 Debug 标记，用于启用模块文档中说明的 Debug 运行时控制。

默认 `python -m build` 会创建隔离构建环境，并在该环境中安装构建依赖。内网或离线环境推荐使用上面的 `--no-isolation`，让构建过程复用当前环境中已经安装好的 `requirements.txt`。

## Debug 运行

Debug 运行需要先构建并安装 Debug wheel，再通过 `OTPD_STUB_MODE=1` 启用桩模式：

```bash
python -m pip install -r requirements.txt
python -m build --wheel --no-isolation -C--build-option=--debug-build
python -m pip install --force-reinstall dist/ublinkdt-1.0.0-py3-none-any.whl
OTPD_STUB_MODE=1 ublinkdt -m otpd -p 0 -c 0 -d 0 --stat
```

## 测试

```bash
python -m pip install pytest pytest-cov
pytest
```

## 项目结构

```text
ublinkdt/
├── src/
│   ├── __init__.py
│   ├── utils/
│   └── otpd/
│       ├── cli.py
│       ├── command_parsers.py
│       ├── field_calculators.py
│       ├── format.py
│       ├── models.py
│       ├── northbound.py
│       ├── southbound.py
│       ├── southbound_commands.py
│       └── system_interface.py
├── tests/
├── docs/
├── requirements.txt
├── setup.py
└── README.md
```

## 未来规划

- 电组网诊断：电缆/背板链路的信号完整性检测
- 故障检测定位：链路故障的自动检测与定位
