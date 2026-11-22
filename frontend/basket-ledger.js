import { act, badge, errorLine, escapeHtml, input, money, planLabels, post } from './promo.js';

function receiptDesk(plan, catalog) {
  const skuOptions = catalog.map(product => `<option value="${escapeHtml(product.sku)}">${escapeHtml(product.sku)} · ${escapeHtml(product.name)}</option>`).join('');
  return `<section class="panel"><h3>录入 POS 小票</h3>
    <form id="receipt-form"><fieldset class="basket-fieldset">
      ${input('receipt_no', '原始小票号', 'maxlength="40" pattern="[A-Za-z0-9][A-Za-z0-9\\-]{2,39}" placeholder="例如 HS-1201-031" required')}
      <div id="receipt-lines"></div>
      <template id="receipt-line"><div class="receipt-line">
        <label class="field"><span>商品 SKU</span><select name="sku" required><option value="">选择商品</option>${skuOptions}</select></label>
        ${input('quantity', '件数', 'type="number" min="1" max="100" value="1" required')}
        <button type="button" class="btn alt small" data-remove-line aria-label="删除商品行">删除</button>
      </div></template>
      <button type="button" class="btn alt small" id="add-receipt-line">添加商品行</button>
      <div class="basket-form-actions actions"><button type="submit" value="quote" class="btn alt">核定小票</button>
        <button type="submit" value="record" class="btn orange" disabled>登记核销</button></div>
    </fieldset>${errorLine}<div id="receipt-quote" role="status" class="note good" hidden></div></form>
    <p class="promo-hint">录入同票的前件商品和立减 SKU ${escapeHtml(plan.sku)}。修改明细后需重新核定。</p>
  </section>`;
}

function transferTrail(transfers, plan) {
  if (!transfers || !transfers.length) return '';
  const rows = transfers.map(t => {
    const outgoing = t.source_plan_id === plan.id;
    const before = outgoing ? t.source_cap_before : t.target_cap_before;
    const after = outgoing ? t.source_cap_after : t.target_cap_after;
    const other = outgoing ? t.target_store_code : t.source_store_code;
    return `<tr>
      <td class="mono">${String(t.created_at).slice(0, 19).replace('T', ' ')}</td>
      <td>${outgoing ? '调出至' : '调入自'} ${escapeHtml(other)}</td>
      <td>${outgoing ? '−' : '+'}${t.transferred_units} 件</td>
      <td>${before} → <b>${after}</b></td>
      <td>${money.format(Number(t.source_unit_discount))} / 件</td>
    </tr>`;
  }).join('');
  return `<section class="panel"><h3>预算调拨记录 <span class="kicker">限量调整前后留痕</span></h3>
    <div class="table-wrap"><table class="promo-table"><thead><tr>
      <th>时间</th><th>方向 / 对手门店</th><th>划拨件数</th><th>本档期限量（前→后）</th><th>单件立减</th>
    </tr></thead><tbody>${rows}</tbody></table></div>
    <p class="promo-hint">历史小票与已退回对账单保留当时金额；新核销和对账按调拨后的限量办理。</p>
  </section>`;
}

function journal(plan, receipts, role) {
  if (role === 'analyst') return '';
  const canVoid = role === 'store_operator' && plan.status === 'active';
  return `<section class="panel basket-journal"><h3>小票流水 <span class="kicker">最近 100 笔</span></h3>
    ${receipts.length ? receipts.map(receipt => `<details ${receipt === receipts[0] ? 'open' : ''}>
      <summary><span class="mono">${escapeHtml(receipt.receipt_no)}</span>
        <span>${receipt.rewarded_units} 件 · ${money.format(receipt.discount_amount)}
          ${receipt.voided_at ? '<span class="status status-rejected">已作废</span>' : '<span class="status status-approved">有效</span>'}</span></summary>
      <div class="basket-receipt-details"><p class="promo-hint">营业日 ${receipt.business_date} · ${receipt.lines.map(line => `${escapeHtml(line.sku)} × ${line.quantity}`).join(' / ')}</p>
        ${receipt.voided_at ? `<p class="promo-hint">作废说明 · ${escapeHtml(receipt.void_reason)}</p>` : canVoid ? `
          <form data-void-receipt="${receipt.id}">
            ${input('reason', '作废说明', 'maxlength="240" placeholder="例如 收银已撤销原小票" required')}
            <button type="submit" class="btn alt small">作废小票</button>${errorLine}
          </form>` : ''}
      </div></details>`).join('') : '<div class="empty">登记成功的小票会保留商品行、折扣和作废记录。</div>'}
  </section>`;
}

function bindReceiptDesk(api, path, refresh, toast) {
  const form = document.querySelector('#receipt-form');
  if (!form) return;
  const lines = form.querySelector('#receipt-lines');
  const add = form.querySelector('#add-receipt-line');
  const template = form.querySelector('#receipt-line');
  const plate = form.querySelector('#receipt-quote');
  const recordButton = form.querySelector('button[value="record"]');
  const alert = form.querySelector('[role="alert"]');
  function invalidate() {
    plate.hidden = true;
    alert.hidden = true;
    recordButton.disabled = true;
  }
  function syncLineButtons() {
    lines.querySelectorAll('[data-remove-line]').forEach(button => { button.disabled = lines.children.length <= 1; });
    add.disabled = lines.children.length >= 50;
  }
  function appendLine() {
    const row = template.content.firstElementChild.cloneNode(true);
    row.querySelector('[data-remove-line]').onclick = () => {
      row.remove();
      invalidate();
      syncLineButtons();
    };
    lines.append(row);
    syncLineButtons();
    invalidate();
    return row;
  }
  appendLine();
  add.onclick = () => appendLine().querySelector('select').focus();
  form.oninput = invalidate;
  form.onsubmit = async event => {
    event.preventDefault();
    const button = event.submitter;
    if (!button || (button.value === 'record' && plate.hidden)) return;
    const data = {
      receipt_no: form.elements.receipt_no.value,
      lines: Array.from(lines.children, row => ({
        sku: row.querySelector('[name="sku"]').value,
        quantity: Number(row.querySelector('[name="quantity"]').value),
      })),
    };
    const isQuote = button.value === 'quote';
    plate.hidden = true;
    let quote;
    const fields = form.querySelector('fieldset');
    fields.disabled = true;
    try {
      await act(form, button, async () => {
        quote = await post(api, `${path}/${isQuote ? 'quote' : 'receipts'}`, data);
      }, () => {
        if (isQuote) {
          plate.textContent = `可核销 ${quote.rewarded_units} 件 · 立减 ${money.format(quote.discount_amount)} · 登记后剩余 ${quote.remaining_after} 件`;
          plate.hidden = false;
        } else {
          toast('小票已记入核销流水');
          refresh();
        }
      });
    } finally {
      fields.disabled = false;
      recordButton.disabled = plate.hidden;
    }
  };
}

export async function basketLedger(context, selectedId) {
  const { api, role, head, shell, refresh, isCurrent, toast } = context;
  const plans = (await api('/basket-offers/plans')).filter(row => row.per_receipt_cap && row.status !== 'cancelled');
  const plan = plans.find(row => row.id === selectedId) ?? plans.find(row => row.status === 'active') ?? plans[0];
  const path = plan ? `/basket-offers/plans/${plan.id}` : null;
  const detail = path ? await api(path) : null;
  if (!isCurrent()) return;
  const canRecord = role === 'store_operator' && plan?.status === 'active';
  shell(head('PROMOTIONS / RECEIPT JOURNAL', '逐票核销流水', '按原始 POS 小票核定折扣和剩余额度，结档时以有效流水核对填报件数。') + `
    <div class="basket-layout basket-ledger-layout">
      <aside class="panel"><h3>逐票促销档期</h3>
        ${plans.length ? `<div class="promo-queue">${plans.map(row => `<button type="button" data-ledger-plan="${row.id}" aria-pressed="${row === plan}">
          <span><b>${escapeHtml(row.store_name)}</b><br><small class="promo-hint">#${row.id} · ${escapeHtml(row.sku)} ${escapeHtml(row.product_name)}</small></span>
          ${badge(planLabels[row.status])}</button>`).join('')}</div>` : '<div class="empty">暂无已启用逐票核销的档期。</div>'}
        <div class="promo-link"><button class="btn alt small" data-page="${plan && plan.status !== 'planned' ? 'settlements' : 'promotions'}" ${plan ? `data-target-id="${plan.id}"` : ''}>${plan && plan.status !== 'planned' ? '查看核销对账' : '查看促销排期'}</button></div>
      </aside>
      <div class="basket-ledger-main">${plan ? `
        <section class="panel"><h3>${escapeHtml(plan.product_name)} · 核销余量</h3>
          <div class="basket-rule-strip"><div><span>有效核销 / 总限量</span><b>${Number(plan.ledger_units)} / ${plan.unit_cap} 件</b></div>
            <div><span>已用折扣</span><b>${money.format(plan.ledger_discount)}</b></div><div><span>有效小票</span><b>${Number(plan.receipt_count)} 张</b></div></div>
          <p class="promo-hint">${detail.requirements.map(row => `${escapeHtml(row.family)} ≥ ${row.minimum_units} 件`).join(' · ')} · 单票最多立减 ${plan.per_receipt_cap} 件</p>
        </section>
        ${canRecord ? receiptDesk(plan, detail.catalog) : ''}${journal(plan, detail.receipts, role)}
        ${transferTrail(detail.transfers, plan)}
      ` : '<section class="panel empty">经理启用逐票核销后，档期和剩余额度会显示在这里。</section>'}</div>
    </div>`);
  document.querySelectorAll('[data-ledger-plan]').forEach(button => {
    button.onclick = () => refresh(Number(button.dataset.ledgerPlan));
  });
  if (canRecord) bindReceiptDesk(api, path, () => refresh(plan.id), toast);
  document.querySelectorAll('[data-void-receipt]').forEach(form => {
    form.onsubmit = event => {
      event.preventDefault();
      const reason = new FormData(form).get('reason');
      act(form, event.submitter, () => post(api, `${path}/receipts/${form.dataset.voidReceipt}/void`, { reason }), () => {
        toast('小票已作废，活动额度已恢复');
        refresh(plan.id);
      });
    };
  });
}
