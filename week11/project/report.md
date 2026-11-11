## 概述

AI操作系统正成为连接大模型与物理/数字世界的关键基础设施。本次调研的五篇论文从不同维度勾勒出该领域的演进路径：从语义化交互层（LUMOS）、垂直领域联邦架构（Telcos）、人机协同执行机制（CrabOS）、OS-Agent生态范式（AIOS）到自然语言驱动的数据生态（AgentOS），共同指向一个核心趋势——传统面向人类的操作系统接口正被重构为面向智能代理的语义化、协作化平台。

## 代表性论文

**1. LUMOS: A Semantic Operating-System Layer for Accessibility-Grounded AI Agents**
链接：http://arxiv.org/abs/2606.30697v1
贡献：首次提出基于可访问性接口构建的语义操作系统层，以紧凑语义状态替代像素级视觉解析，显著提升AI代理的计算机任务执行效率与可靠性。

**2. The Case for a Horizontal Federated AI operating System for Telcos**
链接：http://arxiv.org/abs/2506.17259v1
贡献：针对电信行业AI碎片化问题，提出横向联邦AI操作系统设计，区别于垂直厂商绑定方案，以协作层整合跨域AI能力，为行业级AI部署提供了新范式。

**3. CrabOS: An Operating System for Human-AI Co-inhabitation**
链接：http://arxiv.org/abs/2608.28165v1
贡献：聚焦人机交替主导的真实任务场景，设计显式状态管理与交接协议，解决代理系统缺乏无缝工作状态交接的痛点，为人机协同执行奠定系统基础。

**4. LLM as OS, Agents as Apps: Envisioning AIOS, Agents and the AIOS-Agent Ecosystem**
链接：http://arxiv.org/abs/2312.03815v2
贡献：提出LLM作为操作系统内核、AI代理作为应用的生态愿景，从范式层面重新定义OS-APP关系，是该领域的奠基性理论框架。

**5. AgentOS: From Application Silos to a Natural Language-Driven Data Ecosystem**
链接：http://arxiv.org/abs/2603.08938v2
贡献：针对代理应用孤岛问题，提出以自然语言为交互界面的AgentOS，将代理从独立应用转变为统一数据生态系统，实现与本地环境及外部工具的深度整合。

## 趋势观察

五篇论文共同揭示三大趋势：其一，**接口语义化**——从LUMOS的语义状态到AgentOS的自然语言驱动，操作系统正从"像素界面"转向"意图界面"；其二，**架构层次化**——AIOS提供宏观生态愿景，LUMOS与CrabOS分别解决底层交互与执行协同，Telcos方案则验证了垂直领域的落地路径，形成"理论-机制-应用"的完整链条；其三，**协同常态化**——CrabOS的人机交接与Telcos的联邦协作表明，AI操作系统不仅是工具平台，更是多方智能体的协作中介。值得注意的是，各论文在"语义抽象程度"与"协作粒度"上存在差异：LUMOS聚焦单代理效率，而AIOS与AgentOS追求生态级整合，未来研究需在两者间寻求平衡。