import { act, badge, errorLine, escapeHtml, input, money, planLabels } from './promo.js';

function termsEditor(plan, requirements) {
  const current = new Map(requirements.map(row => [row.family, row.minimum_units]));
  const fields = plan.antecedent.split(' + ').map((family, index) => input(`family-${index}`,
    `${escapeHtml(family)} · 最少件数`, `type="number" min="1" max="100" value="${current.get(family) ?? 1}" required`));
  return `<form id="basket-terms-form">
    <fieldset class="basket-fieldset"><legend>前件商品族</legend><div class="form-row">${fields.join('')}</div></fieldset>
    ${input('per_receipt_cap', '每张小票最多立减件数', `type="number" min="1" max="${Math.min(plan.unit_cap, 100)}" value="${plan.per_receipt_cap ?? 1}" required`)}
    ${errorLine}<button class="btn orange" type="submit">保存并启用逐票核销</button>
  </form>`;
}

export async function basketTerms(context, selectedId) {
  const { api, role, head, shell, refresh, isCurrent, toast } = context;
  if (role !== 'manager') {
    shell(head('PROMOTIONS / OFFER TERMS', '购物篮门槛') + '<div class="empty">购物篮门槛由促销经理配置。</div>');
    return;
  }
  const plans = (await api('/basket-offers/plans')).filter(plan => plan.status !== 'cancelled');
  const plan = plans.find(row => row.id === selectedId) ?? plans.find(row => row.status === 'planned') ?? plans[0];
  const detail = plan ? await api(`/basket-offers/plans/${plan.id}`) : null;
  if (!isCurrent()) return;
  shell(head('PROMOTIONS / OFFER TERMS', '购物篮门槛', '为已排期的规则设置小票门槛。开档后锁定条件，门店按票核销。') + `
    <div class="basket-layout">
      <section class="panel"><h3>选择促销档期</h3>
        ${plans.length ? `<div class="promo-queue">${plans.map(row => `<button type="button" data-offer-plan="${row.id}" aria-pressed="${row === plan}">
          <span><b>${escapeHtml(row.store_name)}</b><br><small class="promo-hint">#${row.id} · ${escapeHtml(row.sku)} ${escapeHtml(row.product_name)}</small></span>
          ${badge(planLabels[row.status])}</button>`).join('')}</div>` : '<div class="empty">发布规则并排期后，可在这里配置门槛。</div>'}
        <div class="promo-link"><button class="btn alt small" data-page="promotions">返回促销排期</button></div>
      </section>
      <section class="panel"><h3>前件与折扣</h3>${plan ? `
        <div class="basket-rule-strip"><div><span>关联规则前件</span><b>${escapeHtml(plan.antecedent)}</b></div>
          <div><span>立减商品</span><b>${escapeHtml(plan.sku)} · ${money.format(plan.unit_discount)} / 件</b></div>
          <div><span>档期总限量</span><b>${plan.unit_cap} 件</b></div></div>
        <p class="promo-hint">${escapeHtml(plan.store_name)} · ${plan.starts_on} 至 ${plan.ends_on} · ${escapeHtml(plan.operator_name)}</p>
        ${plan.status === 'planned' ? termsEditor(plan, detail.requirements) : detail.requirements.length ? `
          <dl class="promo-summary">${detail.requirements.map(row => `<div><dt>${escapeHtml(row.family)}</dt><dd>至少 ${row.minimum_units} 件</dd></div>`).join('')}
          <div><dt>单票立减上限</dt><dd>${plan.per_receipt_cap} 件</dd></div></dl>
          <button class="btn alt" data-page="basket-ledger" data-target-id="${plan.id}">查看核销流水</button>` : '<div class="empty">该档期采用 POS 汇总对账。</div>'}
        ${plan.per_receipt_cap ? '<p class="promo-hint" role="status">逐票核销已启用，结档须核对有效流水件数。</p>' : ''}
      ` : '<div class="empty">创建促销档期后选择需要逐票核销的活动。</div>'}</section>
    </div>`);
  document.querySelectorAll('[data-offer-plan]').forEach(button => {
    button.onclick = () => refresh(Number(button.dataset.offerPlan));
  });
  const form = document.querySelector('#basket-terms-form');
  if (!form) return;
  form.onsubmit = event => {
    event.preventDefault();
    const values = new FormData(form);
    const minimums = Object.fromEntries(plan.antecedent.split(' + ').map((family, index) =>
      [family, Number(values.get(`family-${index}`))]));
    act(form, event.submitter, () => api(`/basket-offers/plans/${plan.id}/terms`, {
      method: 'PUT', body: JSON.stringify({ minimums, per_receipt_cap: Number(values.get('per_receipt_cap')) }),
    }), () => {
      toast('购物篮门槛已保存');
      refresh(plan.id);
    });
  };
}
