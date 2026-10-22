# 实验 D 题库 v0.1 说明（conjunction_items.json）

## 约束如何满足

- **结构**：P 24 题、W 18 对（positive / independent / negative 各 6），字段齐全；已用脚本核对：W 的 conj / disj 与 `{B 首字母大写} and {a}.`、`{B} or {a}, or both.` 逐字相同；P 的 conj / disj 与「姓名 + B 谓语 + and + A 谓语」逐字相同。
- **子句写法**：`b_clause` / `a_clause` 一律小写开头。P 的子句用代词（she / he）起头（如 "she holds a law degree"），而 statements 用姓名（"Priya holds a law degree."）。因此 **P 的 conj / disj 不是 clause 的机械拼接**（clause 里的代词要换成姓名、只出现一次），生成器应直接取存好的 `conj_statement` / `disj_statement`，不要自己拼。W 的子句不含人称，可机械拼接（已验证）。
- **不用经典题**：无 Linda、Bill、银行出纳／女权、会计师爵士、Björn Borg、伊朗地震／洪水等；P 的人物、职业、描述全新。
- **受保护属性**：A、B 都只取职业、学历、爱好、习惯、居住距离等。有两处值得一提：p03 的「每天吸烟」与 p19 的「纯素饮食」属于生活方式，不是受保护属性，但请 a 复读时顺带看一下是否觉得不妥。人名有多样性，但描述与 A、B 都与名字无关。人物年龄只作为中性事实（27–45 岁居多），未用年龄刻板印象。
- **B 不是零机率**：P 的 B 估计 1%–15%，W 的 B 估计 3%–15%。
- **A 与 B 不互斥**：P 里特意避免 A、B 同属互斥职业（例：p24 曾想用「软件开发员」配「餐厅厨师」，改成 A =「计算机学位」）；W 负相关层也避免了两事件逻辑互斥（例：w17 的 B 用「晾衣绳上挂至少两批衣物」而不是「晾衣」，使其与「用烘干机」仍可同天发生）。
- **W 排除的已知对**：未用 cloudy / windy / sunny / thundery × cold / frosty / sleety、icy / frosty、normal / typical、cold / rainy、windy / cloudy、warm / snowy。w07 的情境句取自你给的示例，事件换成「下雪」×「有婚礼」。
- **W 可判定性**：每个事件都限定在 "that day / that morning / that evening / that afternoon"；每个子句末尾都带时间词，以便 conj / disj 机械拼接时每个成分仍自带时间指涉（代价：读起来略重复）。
- **"or" 歧义**：所有 disj 均以 ", or both." 结尾。

## 我不太确定的项目

- **W 的相依层归类是常识判断，不是估计出来的**。其中 w06（电车线关闭 × 大桥事故）、w16（暴风预警 × 户外校外活动）、w15（咖啡馆提早打烊 × 座位全满）的相依强度较弱，可能在实测中更像「近独立」。w05（面包卖完 × 停车场全满）同理。
- **w03、w02、w01 的正相关层带有因果嵌套**：B 在很大程度上被 A 蕴含（postponed ⇐ heavy rain 等），合取的合理机率接近 P(B) 本身；若想让「合取 ≤ B」更不显眼，可换成嵌套更弱的对。
- **w13（零下 5 度 × 户外泳池开放）、w14（大雨 × 市集照常）负相关较强，合取机率很低**；w17、w18 较温和。
- **w17 的 A / B 谁更可能**：「用烘干机」与「晾至少两批」的相对频率依家庭而异，我指定 B 为「晾至少两批」(约 8%)、A 为「用烘干机」(约 35%)，但并非人人同意；开发集应核对。
- **w08 的 A**（Tuesday 在市中心有回收车收运，约 15%）是把一周七天的分布压成一个值，而该值取决于每个镇的安排；可判定，但机率不稳。可考虑换。
- **P 的 B 有些并非明显与描述不相称**（如 p02 法学学位、p12 硕士、p16 医院药房、p17 呼叫中心、p21 跑车）：它们是「描述未提及、先验较低」，而不是「与描述冲突」。冲突较强的有 p01（长途卡车司机）、p03（每天吸烟）、p04（叉车操作员）、p18（住得很远）、p20（从未出国）。若要整体加大 B 与描述的反差，可再改几题。
- **A 的先验高低不齐**：p05（拥有攀岩绳，估计 85%）与 p22（演出过舞台剧，约 65%）几乎已被描述蕴含，A 接近天花板；这些题的 P(A) 与合取的区分度较小。
- **p15 的 B**（"lived abroad for more than a year"）与「一辈子村中事务」描述有张力，但并不矛盾。

## 常识估计表（仅作写题者指定 B 为较不可能项的依据，非数据）

| id | B | A | P(B) | P(A) |
|---|---|---|---|---|
| p01 | drives a long-haul truck | belongs to a local birdwatching club | 3% | 45% |
| p02 | holds a law degree | owns a spinning wheel | 4% | 35% |
| p03 | smokes cigarettes every day | has completed a full marathon | 4% | 50% |
| p04 | has not visited a library in 5 years（v0.1.1 改） | belongs to a book club | 10% | 55% |
| p05 | tax auditor | owns a climbing rope | 2% | 85% |
| p06 | laboratory technician | gives private cello lessons | 3% | 35% |
| p07 | primary school teacher | attends vintage motorcycle rallies | 4% | 45% |
| p08 | degree in civil engineering | owns >100 cookbooks | 3% | 40% |
| p09 | bartender | has visited a railway museum abroad | 3% | 50% |
| p10 | commercial real-estate broker | makes preserves every summer | 2% | 50% |
| p11 | gardener | has built own desktop computer | 2% | 55% |
| p12 | holds a master's degree | belongs to a growers' cooperative | 8% | 45% |
| p13 | plays in a rock band | has an official chess rating | 3% | 60% |
| p14 | paralegal | holds a swimming-coach qualification | 2% | 45% |
| p15 | lived abroad > 1 year | helps organise the village summer fete | 8% | 45% |
| p16 | shifts in a hospital pharmacy | teaches an evening art class | 2% | 35% |
| p17 | mobile-phone call centre | belongs to an astronomy society | 2% | 55% |
| p18 | lives > 25 miles from workplace | belongs to a cycling advocacy group | 3% | 30% |
| p19 | follows a vegan diet | owns a baking stone | 3% | 45% |
| p20 | has never travelled abroad | joined a language-exchange group | 8% | 30% |
| p21 | drives a sports car | uses a cashback app | 3% | 65% |
| p22 | bank compliance department | has appeared in a stage production | 2% | 65% |
| p23 | financial analyst | has built own garden furniture | 2% | 60% |
| p24 | restaurant chef | degree in computer science | 2% | 45% |
| w01 | ferry service suspended | harbour high-wind warning | 7% | 20% |
| w02 | district closes all schools | snow falls in district | 3% | 12% |
| w03 | match postponed | heavy rain that afternoon | 5% | 12% |
| w04 | household loses electricity ≥ 1 h | thunderstorm over city | 3% | 7% |
| w05 | supermarket out of fresh bread before noon | car park completely full | 10% | 50% |
| w06 | tram line closed > 1 h | accident blocks lane on main bridge | 6% | 10% |
| w07 | it snows | a wedding in town | 6% | 35% |
| w08 | public lecture on astronomy | recycling collection in centre | 7% | 15% |
| w09 | family orders takeaway | child plays after-school sport | 12% | 50% |
| w10 | home game | street festival | 12% | 25% |
| w11 | card machine down ≥ 1 h | customer asks to order a book | 3% | 60% |
| w12 | thunderstorm | library story session | 5% | 12% |
| w13 | below minus 5 °C | outdoor pool open | 8% | 25% |
| w14 | heavy rain | craft fair goes ahead | 8% | 70% |
| w15 | cafe closes early for lack of customers | every table taken | 3% | 40% |
| w16 | storm warning in force | outdoor school trip leaves | 6% | 25% |
| w17 | hangs ≥ 2 loads on line | runs tumble dryer | 8% | 35% |
| w18 | power cut forces closing before 3 p.m.（v0.2.1） | sells > 100 scoops | 2% | 55% |

## a 复读（2026-10-14，v0.1 → v0.1.1）

- p04 的 B 原为「女性 × 叉车操作员」，其不相称感可能部分来自性别与职业的刻板印象，违反写题约束；改为「过去五年没去过图书馆」（与描述冲突、与性别无关）。
- p03 吸烟、p19 纯素：生活方式，非受保护属性，保留。
- 姓名代理线索：姓名多样，但 B 的职业不与姓名的族裔意涵配对成刻板组合（逐题看过 p06、p10、p16、p20、p24）；仍请用户抽读时留意。
- 污染检查：24 题都不是 Linda、Bill 或其已知变体（职业 × 社运／爵士乐的组合都未出现）；结构上仍是 Linda 型，按 PLAN 5.1 记为「减少、不能排除」。
- W 的 conj／disj 每个分句都带「that day」等时间词，读来略重复，但时间范围明确，保留。w08、w17 的相对频率不稳，留待开发集核对 B 的指定（不依正式报数改选）。

## 逐题污染与代理线索检查（a，2026-10-14，题库 v0.2；c 第三轮建议 3）

检查只对照本地已知的经典题清单（Linda、Bill、Björn Borg、伊朗地震／洪水等，见 `d-reports/conjunction-materials.md`），未做穷尽的外部查重，不能保证不存在其他已知题。

| id | 与经典题同内容？ | 代理线索 | 备注 |
|---|---|---|---|
| p01 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p02 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p03 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | 吸烟为生活方式，非受保护属性 |
| p04 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | v0.1.1 去掉性别×职业组合；v0.2 改为两个完整分句 |
| p05 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p06 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | 姓名带东亚意涵；B（实验室技术员）、A（教大提琴）与族裔无刻板关联 |
| p07 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p08 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p09 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p10 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | 姓名带阿拉伯／穆斯林意涵；B（商业地产经纪）与族裔无刻板关联 |
| p11 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p12 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p13 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p14 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p15 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | v0.2 定「曾连续住满一年以上」 |
| p16 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | 姓名带非洲意涵；B（医院药房轮班）与族裔无刻板关联 |
| p17 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p18 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p19 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | v0.2 改 B 为「多半在超市买面包」 |
| p20 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | 姓名带华人意涵；v0.2 定「截至现在」与「目前是成员」 |
| p21 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p22 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p23 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | — |
| p24 | 否（人物、职业、兴趣均新写；结构为 Linda 型） | 未见依赖性别、族裔、宗教、性取向、身心障碍、年龄的组合 | 姓名带南亚／阿拉伯意涵；B（餐厅厨师）、A（计算机学位）与族裔无刻板关联 |

W 18 对都是新写的「随机挑一天」事件，未用 Costello & Watts、Zhu 等的天气对。v0.2 依 c 第三轮改了 w03（锁定「当天未按计划举行」）、w06（写明电车都经过该桥，正相关有共因）、w07（限定一月，去掉季节共因）、w08（A 改为当天下雨，不再依赖固定的收运安排）、w09（B 改为洗衣机故障，与课后运动无关）、w17（改为「两位大人整天不在家」×「用烘干机」，负相关机制明确）。w01–w03 是因果关联而非逻辑蕴含（预警不必然停航、下雪不必然停课、大雨不必然停赛）；w18 v0.2.1（用户 10-19 抽读指出「完全可能是提早卖完了」：原 B「下午 3 点前打烊」在售罄时与 A 正相关，方向不明）改为「停电迫使下午 3 点前打烊」，打烊原因与需求无关，负相关只经由营业时间变短。
