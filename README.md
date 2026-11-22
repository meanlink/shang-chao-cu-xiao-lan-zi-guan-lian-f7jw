# 商超促销篮子关联

面向「邻里优选」连锁商超运营团队的购物篮关联规则工作台。系统把门店订单明细沉淀为购物篮，按商品族计算 Apriori 关联规则，经运营审核后生成可执行的搭售建议，并在支持度不足或跨门店口径不一致时禁止发布。演示团队覆盖海淀、朝阳、徐汇三家门店。分析员用日报筛候选，经理依据样本定档期，指定门店执行人核对小票与收银日报。

## 场景与模块

- **订单导入**：接收门店 POS 每日 `orders_2026-11-20.csv`，校验门店、商品族和订单完整性，形成购物篮。
- **商品目录**：维护商品族、SKU 与门店价格，保证算法按商品族聚合而不是按临时名称匹配。
- **关联规则工作台**：运行 Apriori，查看支持度、置信度、提升度和门店口径一致性，提交候选规则。
- **促销审核**：运营经理审核并发布规则，发布后可供门店排期使用。
- **门店促销排期**：经理从已发布规则的后件中选在售 SKU，指定门店、执行人、档期、单件立减和限量。可在开档前取消。执行人在北京时间约定档期内确认开档。
- **购物篮门槛**：经理开档前为规则的每个前件商品族设最低件数，并设单票立减上限。保存即启用该档期的逐票核销，开档后条件锁定。
- **逐票核销流水**：指定执行人录入本营业日的 POS 小票号和 SKU 件数。核定展示立减件数、金额与登记后的余量。登记会重新校验；门店作废时保留原商品行及作废说明，同时归还档期限量。
- **跨店预算调拨**：经理在档期工作台把一家门店仍在执行的逐票促销预算，整建制划拨给另一家门店同款、同单件立减的在执行档期。两档期限量在同一事务内按行锁原子增减，任一侧校验失败两边余额都不变；客户端请求编号保证超时重试不重复划拨。新核销与对账按调拨后限量办理，原小票和已退回对账单保留当时金额，档期可查每笔调拨前后的限量。
- **促销核销对账**：指定执行人登记 POS 对账凭证和实际核销件数，经理确认并结档，或退回门店更正。分析员可查看档期和对账结果。

主流程是订单明细 → 规则计算 → 运营审核 → 门店排期和开档 → POS 核销复核。组合支持度小于 8% 或各门店支持度偏差超过 12 个百分点时，后端将规则标记为阻断，审核通过也不能发布。

同一门店、同一后件 SKU 的未结档档期不能重叠。档期最多 31 天，立减金额最高为锁定目录单价的 50%。核销件数不能超过限量。同店 POS 凭证不得跨档期复用，提前结档或零核销需记录原因。预留折扣 = 单件立减 × 限量，实耗折扣 = 单件立减 × 实际核销件数。核销商品净销售额仅按锁定目录价和折扣计算。

启用逐票核销后，同票各前件商品族的在售 SKU 购入件数分别累加，立减件数取立减 SKU 件数与单票上限的较小值。若额度不足，整票拒绝。同一门店的小票号只能登记一次，按同档期、同商品行重试会返回已有流水。提交对账时 POS 填报件数必须等于未作废流水之和。待复核和已结档时锁定流水，退回才恢复门店的更正操作。历史档期和未启用逐票核销的新档期使用原有 POS 汇总对账。

跨店预算调拨只允许在两个不同门店、同 SKU、同单件立减且仍在执行（执行中或待对账、未超出档期日期）的档期之间进行，划拨额为整件，调出方划拨后至少保留 1 件限量、调入方不超过 100000 件。服务层先按档期 id 顺序加行锁再校验，避免反向并发调拨死锁；与小票登记、对账提交并发时以行锁串行化，已用核销加划拨总量不超过原限量。`request_key` 唯一约束配合事务内复查实现幂等，重复请求回放原单据而不二次划拨。每笔调拨在 `promotion_budget_transfers` 留痕两边限量的前后值并写入审计日志。

### 早餐搭售演练

1. 分析员从 `orders_2026-11-20.csv` 的已播种购物篮检查咖啡、乳品与早餐烘焙的共现。
2. 经理通过并发布「咖啡与冲调 + 乳品 → 早餐烘焙」规则，为朝阳望京店的 `BK-002` 安排当日促销，每件立减 ¥3，限量 12 件。
3. 经理设置咖啡与冲调至少 2 件、乳品至少 1 件，每票最多立减 2 件。
4. 徐琳确认开档。小票 `UI-CY-027` 上的 1 件咖啡达不到门槛。核对原票改为 2 件咖啡、1 件乳品和 3 件 `BK-002` 后，可立减 ¥6。
5. 徐琳登记该票，并作废一张收银已撤销的小票，保留原明细。有效核销合计 2 件。
6. 徐琳提交 `UI-BASKET-CY` 收银日报。系统拦截 3 件的填报，按 2 件重报成功。
7. 经理核定实耗 ¥6 和剩余额度 ¥30，确认结档。

## 快速启动

```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python scripts/seed_demo.py
curl http://localhost:19245/health
```

访问 `http://localhost:18245`。演示账号如下，密码均为 `basket123`。

| 账号 | 角色 | 权限 |
|---|---|---|
| `ops@linli.local` | analyst | 导入订单、运行关联计算、提交规则、查看档期、对账与逐票汇总 |
| `manager@linli.local` | manager | 审核和发布规则、排期和取消、设置逐票门槛、查看流水、复核或退回对账 |
| `store@linli.local`、`store-east@linli.local` | store_operator | 查看本人获分配的档期、确认开档、核定登记与作废小票、提交和更正核销对账 |

## 技术栈与目录

| 层 | 技术 |
|---|---|
| 前端 | Nginx + 原生 HTML/CSS/ES modules |
| 后端 | Python 3.11 + FastAPI + PyMySQL |
| 数据库 | MySQL 8.0 |
| 任务与缓存 | Redis 7 + heartbeat worker |
| 鉴权 | JWT 结构化 token（HMAC-SHA256）+ 三角色权限 |

`backend/src/db.py` 初始化原有表和 `backend/src/models/promotion.py` 中的扩展表，已有库启动时自动补表。`backend/src/services/association.py` 实现 Apriori。排期与对账使用 `/promotions` 下的接口，输入模型、业务状态和事务分别在 `backend/src/schemas/promotion.py` 和 `backend/src/services/promotion.py`。原生页面由 `frontend/app.js` 路由，`frontend/promo.js` 渲染排期及对账。`backend/src/constants/enums.py` 的 `RuleStatus` 与 `UserRole` 对应 `frontend/app.js` 的状态与角色标签。`PromotionStatus` 和 `SettlementStatus` 对应 `frontend/promo.js` 的状态标签及扩展表的状态列。`backend/src/models/basket_offer.py` 和 `basket_receipt.py` 定义逐票促销条件及小票证据。`/basket-offers` 路由连接 `basket_terms.py`、`basket_qualification.py`、`basket_receipts.py`、`basket_ledger.py`，供 `frontend/basket-terms.js` 和 `frontend/basket-ledger.js` 渲染。跨店预算调拨由 `backend/src/models/budget_transfer.py` 建表、`backend/src/services/budget_transfer.py` 实现原子与幂等逻辑，接口挂在 `/promotions/budget-transfer` 下，前端页面为 `frontend/budget-transfer.js`。

## 环境变量

`.env.example` 定义前端、后端和数据库端口、MySQL 凭据、Redis 地址与 seed 开关。容器之间通过 Compose 网络访问，宿主机访问端口为 18245、19245、17745。

## 本地开发

```bash
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload
```

## 测试

调拨功能的单元与并发测试在 `backend/tests/`，需要一个可连通的 MySQL/MariaDB 实例（测试库 `supermarket_basket_test` 自动创建并逐用例清空）：

```bash
cd backend
pip install -r requirements.txt pytest httpx
MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 \
TEST_DB_ADMIN_SOCKET=/var/run/mysqld/mysqld.sock \
pytest tests/ -q
# 真实 HTTP 端到端冒烟（独立库 supermarket_basket_smoke）
python tests/smoke_e2e.py
```

`TEST_DB_ADMIN_SOCKET`、`TEST_DB_ADMIN_USER`、`TEST_DB_ADMIN_PASSWORD` 用于建库授权；应用账号本身具备建库权限时可省略。

## License

Internal demonstration project.
