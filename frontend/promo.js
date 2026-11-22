const planLabels = {
  planned: ['待开档', 'draft'], active: ['执行中', 'approved'],
  settling: ['待对账', 'submitted'], closed: ['已结档', 'published'],
  cancelled: ['已取消', 'rejected'],
};
const reportLabels = {
  submitted: ['待复核', 'submitted'], returned: ['退回更正', 'rejected'],
  confirmed: ['已确认', 'published'],
};
const money = new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' });
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]);
const badge = ([label, color]) => `<span class="status status-${color}">${label}</span>`;
const option = (row, label) => `<option value="${row.id}">${escapeHtml(label)}</option>`;
const select = (name, label, options) => `
  <label class="field"><span>${label}</span><select name="${name}" required>
  <option value="">请选择</option>${options}</select></label>`;
const input = (name, label, attrs) => `
  <label class="field"><span>${label}</span><input name="${name}" ${attrs}></label>`;
const errorLine = '<p class="promo-error" role="alert" hidden></p>';
const post = (api, path, data) => api(path, {
  method: 'POST', ...(data ? { body: JSON.stringify(data) } : {}),
});

async function act(container, button, task, onSuccess) {
  const alert = container.querySelector('[role="alert"]');
  alert.hidden = true;
  button.disabled = true;
  try {
    await task();
    onSuccess();
  } catch (error) {
    alert.textContent = error.message;
    alert.hidden = false;
  } finally {
    button.disabled = false;
  }
}

function renderPlanForm(options) {
  if (!options.rules.length) {
    return '<div class="empty">发布一条关联规则后，就可以安排门店试促。</div><button class="btn alt promo-link" data-page="reviews">前往促销审核</button>';
  }
  return `<form id="promotion-plan-form">
    ${select('rule_id', '已发布规则', options.rules.map(r => option(r, `${r.antecedent} → ${r.consequent}`)).join(''))}
    ${select('product_id', '规则后件 SKU', '')}
    <p class="promo-hint" id="sku-price" aria-live="polite"></p>
    ${select('store_id', '试促门店', options.stores.map(s => option(s, `${s.name} · ${s.code}`)).join(''))}
    ${select('operator_id', '指定执行人', options.operators.map(u => option(u, u.display_name)).join(''))}
    <div class="form-row">
      ${input('starts_on', '开档日', `type="date" min="${options.today}" value="${options.today}" required`)}
      ${input('ends_on', '结束日', `type="date" min="${options.today}" value="${options.today}" required`)}
    </div>
    <div class="form-row">
      ${input('unit_discount', '每件立减（元）', 'type="number" min="0.01" step="0.01" required')}
      ${input('unit_cap', '活动限量（件）', 'type="number" min="1" max="100000" required')}
    </div>
    ${errorLine}<button type="submit" class="btn orange">确认排期</button>
  </form>`;
}

export { act, badge, errorLine, escapeHtml, input, money, planLabels, post };

function planActions(plan, role) {
  if (role === 'manager' && plan.status === 'planned') return `<button class="btn alt small" data-page="basket-terms" data-target-id="${plan.id}">设置购物篮门槛</button> <button class="btn alt small" data-action="cancel">取消档期</button>`;
  if (role === 'store_operator' && plan.status === 'planned') return '<button class="btn small green" data-action="activate">确认开档</button>';
  if (['active', 'settling', 'closed'].includes(plan.status)) return `<button class="btn alt small" data-page="settlements" data-target-id="${plan.id}">查看对账</button>`;
  return '—';
}

export async function promotionPlans({ api, role, head, shell, toast, refresh, isCurrent }) {
  const [plans, options] = await Promise.all([api('/promotions/plans'), role === 'manager' ? api('/promotions/plan-options') : null]);
  if (!isCurrent()) return;
  const side = options ? `<h3>新增试促档期</h3>${renderPlanForm(options)}` : `
    <h3>开档检查</h3><div class="note">按北京时间开档。执行人先在店内确认价签、备货和促销限量，再点击确认开档。</div>
    <div class="promo-link"><button class="btn alt small" data-page="settlements">查看核销对账</button></div>`;
  shell(head('PROMOTIONS / STORE ROLLOUT', '门店促销排期', '把已发布的搭售规则落实到门店、商品、档期和指定执行人。') + `
    <div class="grid">
      <section class="panel span-8"><h3>门店执行清单 <span class="kicker">${plans.length} 条</span></h3>
        ${plans.length ? `<div class="table-wrap"><table class="promo-table"><thead><tr>
          <th>门店 / 档期</th><th>搭售目标</th><th>限量 / 预留</th><th>状态 / 动作</th>
        </tr></thead><tbody>${plans.map(p => `<tr data-plan="${p.id}">
          <td><b>${escapeHtml(p.store_name)}</b><br><span class="mono">${p.starts_on}<br>至 ${p.ends_on}</span></td>
          <td><b>${escapeHtml(p.product_name)}</b><br><span class="promo-hint">${escapeHtml(p.sku)} · ${escapeHtml(p.consequent)}</span>
            <br><span class="promo-hint">规则 #${p.rule_id} · ${escapeHtml(p.operator_name)}</span></td>
          <td>${p.unit_cap} 件 × ${money.format(p.unit_discount)}<br><b>${money.format(p.reserved_discount)}</b></td>
          <td>${badge(planLabels[p.status])}<div class="promo-action">${planActions(p, role)}</div></td>
        </tr>`).join('')}</tbody></table></div>${errorLine}` : '<div class="empty">当前没有可查看的档期。经理排期并指定执行人后，记录会出现在这里。</div>'}
        <div class="note promo-policy">同店同 SKU 的未结档促销不可重叠。单件立减最高为目录单价的 50%，预留额度等于单件立减乘以限量。</div>
      </section>
      <section class="panel span-4">${side}</section>
    </div>`);
  const form = document.querySelector('#promotion-plan-form');
  if (form) {
    const { rule_id: ruleSelect, product_id: skuSelect } = form.elements;
    const price = form.querySelector('#sku-price');
    const showPrice = () => {
      const product = options.products.find(p => String(p.id) === skuSelect.value);
      price.textContent = product ? `目录单价 ${money.format(product.price)}` : '选择规则以查看匹配商品';
    };
    ruleSelect.onchange = () => {
      const rule = options.rules.find(r => String(r.id) === ruleSelect.value);
      skuSelect.replaceChildren(new Option('请选择', ''), ...options.products.filter(p => p.family === rule?.consequent)
        .map(p => new Option(`${p.name} · ${p.sku}`, p.id)));
      showPrice();
    };
    skuSelect.onchange = showPrice;
    showPrice();
    form.onsubmit = event => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(form));
      act(form, event.submitter, () => post(api, '/promotions/plans', data), () => {
        toast('已排期，指定执行人可在档期内开档');
        refresh();
      });
    };
  }
  document.querySelectorAll('tr[data-plan] [data-action]').forEach(button => {
    button.onclick = () => act(button.closest('section'), button,
      () => post(api, `/promotions/plans/${button.closest('tr').dataset.plan}/${button.dataset.action}`), () => {
        toast(button.dataset.action === 'activate' ? '已开档，可提交核销对账' : '档期已取消');
        refresh();
      });
  });
}

function renderReconciliation(row, role) {
  if (!row) return '<div class="empty">门店确认开档后，可在这里登记 POS 核销凭证和核销量。</div>';
  const summary = row.id ? `<dl class="promo-summary">
    <div><dt>POS 对账凭证</dt><dd class="mono">${escapeHtml(row.pos_reference)}</dd></div>
    <div><dt>核销件数</dt><dd>${row.redeemed_units} / ${row.unit_cap} 件</dd></div>
    <div><dt>实耗折扣</dt><dd>${money.format(row.actual_discount)}</dd></div>
    <div><dt>档期剩余额度</dt><dd>${money.format(row.unspent_discount)}</dd></div>
    <div><dt>核销商品净销售额</dt><dd>${money.format(row.promo_net_sales)}</dd></div>
    </dl>${row.note ? `<p class="promo-hint">门店说明 · ${escapeHtml(row.note)}</p>` : ''}` : '';
  const ledger = row.ledger_units == null ? '' : `<div class="note promo-policy">逐票核销有效件数 · ${Number(row.ledger_units)} 件。POS 填报须与有效流水一致。 <button class="btn alt small" data-page="basket-ledger" data-target-id="${row.plan_id}">查看流水</button></div>`;
  const feedback = row.review_note ? `<div class="note ${row.status === 'returned' ? 'bad' : 'good'}">复核意见 · ${escapeHtml(row.review_note)}</div>` : '';
  let controls = '';
  if (role === 'store_operator' && row.plan_status === 'active') {
    controls = `<form id="settlement-form">
      ${input('pos_reference', 'POS 对账凭证号', `maxlength="40" pattern="[A-Za-z0-9][A-Za-z0-9\\-]{2,39}" value="${escapeHtml(row.pos_reference)}" required`)}
      ${input('redeemed_units', '核销件数', `type="number" min="0" max="${row.unit_cap}" value="${row.redeemed_units ?? ''}" required`)}
      ${input('note', '门店说明（提前结档或零核销必填）', `maxlength="240" value="${escapeHtml(row.note)}"`)}
      ${errorLine}<button type="submit" class="btn orange">${row.id ? '提交更正' : '提交对账'}</button>
    </form>`;
  }
  if (role === 'manager' && row.status === 'submitted') {
    controls = `<form id="settlement-form">
      ${input('note', '复核意见（退回必填）', 'maxlength="240"')}
      ${errorLine}<div class="actions"><button class="btn green" value="confirm">确认并结档</button>
        <button class="btn alt" value="return">退回更正</button></div>
    </form>`;
  }
  return `<div class="promo-heading"><b>${escapeHtml(row.store_name)} · ${escapeHtml(row.product_name)}</b>
    ${row.status ? badge(reportLabels[row.status]) : badge(planLabels[row.plan_status])}</div>
    <div class="promo-hint">档期 #${row.plan_id} · 截止 ${row.ends_on} · 限量 ${row.unit_cap} 件</div>
    ${ledger}${summary}${feedback}${controls}`;
}

export async function promotionSettlements({ api, role, head, shell, toast, refresh, isCurrent }, selectedId) {
  const rows = await api('/promotions/settlements');
  if (!isCurrent()) return;
  const selected = rows.find(r => r.plan_id === selectedId) ?? rows[0];
  shell(head('PROMOTIONS / POS RECONCILIATION', '促销核销对账', '以门店 POS 对账凭证核定实际折扣支出，复核通过后关闭促销档期。') + `
    <div class="grid">
      <section class="panel span-5"><h3>核销队列</h3>
        ${rows.length ? `<div class="promo-queue">${rows.map(r => `<button type="button" data-settlement="${r.plan_id}"
          aria-pressed="${r === selected}"><span><b>${escapeHtml(r.store_name)}</b><br><span class="promo-hint">
          #${r.plan_id} · ${escapeHtml(r.sku)} ${escapeHtml(r.product_name)}</span></span>
          ${r.status ? badge(reportLabels[r.status]) : '<span class="status status-draft">待门店填报</span>'}
        </button>`).join('')}</div>` : '<div class="empty">暂无已开档促销。</div>'}
        <div class="note promo-policy">实耗折扣 = 核销件数 × 单件立减。净销售额按排期时锁定的目录价扣减折扣计算，仅涵盖已核销商品。</div>
      </section>
      <section class="panel span-7"><h3>对账单</h3>${renderReconciliation(selected, role)}</section>
    </div>`);
  document.querySelectorAll('[data-settlement]').forEach(button => {
    button.onclick = () => {
      const id = Number(button.dataset.settlement);
      if (id !== selected.plan_id) refresh(id);
    };
  });
  const form = document.querySelector('#settlement-form');
  if (!form) return;
  form.onsubmit = event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    const review = role === 'manager';
    if (review) data.decision = event.submitter.value;
    act(form, event.submitter, () => post(api, `/promotions/settlements/${selected.plan_id}/${review ? 'review' : 'submit'}`, data), () => {
      toast(review ? (data.decision === 'confirm' ? '对账已确认，促销已结档' : '已退回门店更正') : '已提交经理复核');
      refresh(selected.plan_id);
    });
  };
}
