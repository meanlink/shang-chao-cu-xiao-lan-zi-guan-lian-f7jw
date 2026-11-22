import { act, badge, errorLine, escapeHtml, input, money, planLabels, post } from './promo.js';

const requestKey = () => (globalThis.crypto?.randomUUID?.()
  ?? `bt-${Date.now()}-${Math.random().toString(16).slice(2)}`);

function planBalance(p) {
  return `<div class="transfer-balance">
    <div><span>档期限量（当前）</span><b>${p.unit_cap} 件</b></div>
    <div><span>有效核销</span><b>${Number(p.ledger_units)} 件</b></div>
    <div><span>剩余可划拨</span><b>${p.remaining_units} 件</b></div>
    <div><span>单件立减 / 预留</span><b>${money.format(p.unit_discount)} · ${money.format(p.unit_cap * p.unit_discount)}</b></div>
  </div>`;
}

function transferForm(plans) {
  const sources = plans.filter(p => p.partners.length);
  if (!sources.length) {
    return '<div class="empty">暂无可调拨组合：需要两家门店存在同款 SKU、相同单件立减且仍在执行的逐票档期。</div>';
  }
  const sourceOptions = sources.map(p =>
    `<option value="${p.id}">#${p.id} ${escapeHtml(p.store_name)} · ${escapeHtml(p.sku)} ${escapeHtml(p.product_name)}</option>`).join('');
  return `<form id="budget-transfer-form">
    <label class="field"><span>调出档期（预算快用完的门店为调入方时请反向选择）</span>
      <select name="source_plan_id" required><option value="">请选择调出档期</option>${sourceOptions}</select></label>
    <label class="field"><span>调入档期</span>
      <select name="target_plan_id" required><option value="">请先选择调出档期</option></select></label>
    ${input('transferred_units', '划拨件数（整件）', 'type="number" min="1" value="1" required')}
    <input type="hidden" name="request_key" value="${requestKey()}">
    ${input('note', '调拨说明（可选）', 'maxlength="240"')}
    <p class="promo-hint" id="transfer-quote" aria-live="polite"></p>
    ${errorLine}<button type="submit" class="btn orange">确认划拨</button>
    <p class="promo-hint">请求编号 <span class="mono" id="request-key-show"></span>，网络超时重试不会重复划拨。</p>
  </form>`;
}

function historyTable(rows) {
  if (!rows.length) return '<div class="empty">调拨成功后，两边档期的限量变化和操作人会留痕在这里。</div>';
  return `<div class="table-wrap"><table class="promo-table"><thead><tr>
    <th>时间 / 编号</th><th>调出 → 调入</th><th>商品</th><th>划拨件数 / 预算</th>
    <th>调出限量（前→后）</th><th>调入限量（前→后）</th><th>操作人 / 备注</th>
  </tr></thead><tbody>${rows.map(t => `<tr>
    <td class="mono">${String(t.created_at).slice(0, 19).replace('T', ' ')}<br>#${t.id}</td>
    <td><b>${escapeHtml(t.source_store_name)}</b><br>→ ${escapeHtml(t.target_store_name)}
      <br><span class="promo-hint">档期 #${t.source_plan_id} → #${t.target_plan_id}</span></td>
    <td>${escapeHtml(t.sku)}<br><span class="promo-hint">${escapeHtml(t.product_name)}</span></td>
    <td><b>${t.transferred_units} 件</b><br>${money.format(t.transferred_units * Number(t.source_unit_discount))}</td>
    <td>${t.source_cap_before} → <b>${t.source_cap_after}</b></td>
    <td>${t.target_cap_before} → <b>${t.target_cap_after}</b></td>
    <td>${escapeHtml(t.operator_name)}${t.note ? `<br><span class="promo-hint">${escapeHtml(t.note)}</span>` : ''}</td>
  </tr>`).join('')}</tbody></table></div>`;
}

export async function budgetTransfer({ api, role, head, shell, toast, refresh, isCurrent }) {
  const [plans, history] = await Promise.all([
    api('/promotions/budget-transfer/plans'),
    api('/promotions/budget-transfer/history'),
  ]);
  if (!isCurrent()) return;
  const sources = plans.filter(p => p.partners.length);
  shell(head('PROMOTIONS / BUDGET TRANSFER', '跨店预算调拨', '把仍在执行的同款逐票促销预算，按相同单件立减整建制划拨给另一家门店。任一侧失败两边余额都不变。') + `
    <div class="grid">
      <section class="panel span-8"><h3>执行中档期与余额 <span class="kicker">${plans.length} 条可参与</span></h3>
        ${plans.length ? `<div class="table-wrap"><table class="promo-table"><thead><tr>
          <th>门店 / 档期</th><th>商品 / 立减</th><th>余额</th><th>状态</th><th>可调拨门店</th>
        </tr></thead><tbody>${plans.map(p => `<tr>
          <td><b>${escapeHtml(p.store_name)}</b><br><span class="mono">#${p.id} · ${escapeHtml(p.store_code)}</span></td>
          <td>${escapeHtml(p.sku)} ${escapeHtml(p.product_name)}<br><span class="promo-hint">${money.format(p.unit_discount)} / 件</span></td>
          <td>${planBalance(p)}</td>
          <td>${badge(planLabels[p.status])}</td>
          <td>${p.partners.length ? p.partners.map(id => {
            const partner = plans.find(q => q.id === id);
            return partner ? escapeHtml(partner.store_name) : '';
          }).join('、') : '<span class="promo-hint">无匹配档期</span>'}</td>
        </tr>`).join('')}</tbody></table></div>`
          : '<div class="empty">当前没有仍在执行的逐票促销档期。</div>'}
        <div class="note promo-policy">仅同 SKU、同单件立减、不同门店且仍在执行（执行中/待对账、未超出档期日期）的两个档期可互相划拨；划拨额为整件，调出方划拨后至少保留 1 件限量。</div>
      </section>
      <section class="panel span-4"><h3>发起调拨</h3>
        ${role === 'manager' ? transferForm(plans) : '<div class="empty">预算划拨由促销经理发起。</div>'}
      </section>
      <section class="panel span-12"><h3>调拨留痕 <span class="kicker">保留两边调拨前后余额</span></h3>${historyTable(history)}</section>
    </div>`);
  const form = document.querySelector('#budget-transfer-form');
  const keyShow = document.querySelector('#request-key-show');
  if (keyShow) keyShow.textContent = form.elements.request_key.value;
  if (!form) return;
  const sourceSelect = form.elements.source_plan_id;
  const targetSelect = form.elements.target_plan_id;
  const unitsInput = form.elements.transferred_units;
  const quote = document.querySelector('#transfer-quote');
  const syncTargets = () => {
    const source = sources.find(p => String(p.id) === sourceSelect.value);
    targetSelect.replaceChildren(new Option('请选择调入档期', ''),
      ...(source ? source.partners.map(id => plans.find(p => p.id === id))
        .filter(Boolean).map(p => new Option(`#${p.id} ${p.store_name} · ${p.sku}`, p.id)) : []));
    if (source) {
      unitsInput.max = Math.max(1, Math.min(source.remaining_units, source.unit_cap - 1));
      unitsInput.value = Math.min(Number(unitsInput.value) || 1, Number(unitsInput.max));
    }
    updateQuote();
  };
  const updateQuote = () => {
    const source = sources.find(p => String(p.id) === sourceSelect.value);
    const target = plans.find(p => String(p.id) === targetSelect.value);
    const units = Number(unitsInput.value) || 0;
    if (!source || !target || !units) { quote.textContent = ''; return; }
    quote.textContent = `划拨 ${units} 件 × ${money.format(source.unit_discount)} = ${money.format(units * source.unit_discount)}；`
      + `调出限量 ${source.unit_cap}→${source.unit_cap - units}，调入限量 ${target.unit_cap}→${target.unit_cap + units}`;
  };
  sourceSelect.onchange = syncTargets;
  targetSelect.onchange = updateQuote;
  unitsInput.oninput = updateQuote;
  form.onsubmit = event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    data.source_plan_id = Number(data.source_plan_id);
    data.target_plan_id = Number(data.target_plan_id);
    data.transferred_units = Number(data.transferred_units);
    let result;
    act(form, event.submitter, async () => {
      result = await post(api, '/promotions/budget-transfer', data);
    }, () => {
      toast(result.replayed ? '该请求已处理，未重复划拨' : `已划拨 ${result.transferred_units} 件，两边余额已更新`);
      refresh();
    });
  };
}
