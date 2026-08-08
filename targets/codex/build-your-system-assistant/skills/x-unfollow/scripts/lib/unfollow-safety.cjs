'use strict';

const UNFOLLOW_CONFIRM_CONTAINER_SELECTOR = '[role="dialog"],[role="alertdialog"],[data-testid="confirmationSheetDialog"]';

function isExactUnfollowControl(control, handle) {
  const label = String((control && control.ariaLabel) || '').trim();
  const target = String(handle || '').replace(/^@/, '').toLowerCase();
  const match = label.match(/^(?:Unfollow|Following|取消关注|取消關注|取消跟随|取消跟隨|正在关注|正在關注|正在跟随|正在跟隨|已关注|已關注|已跟随|已跟隨)\s+@([A-Za-z0-9_]{1,15})\s*$/i);
  return Boolean(match && target && match[1].toLowerCase() === target);
}

function isExactFollowControl(control, handle) {
  const label = String((control && control.ariaLabel) || '').trim();
  const target = String(handle || '').replace(/^@/, '').toLowerCase();
  const match = label.match(/^(?:Follow|关注|關注|跟随|跟隨)\s+@([A-Za-z0-9_]{1,15})\s*$/i);
  return Boolean(match && target && match[1].toLowerCase() === target);
}

function isExactUnfollowConfirmation(text, handle) {
  const body = String(text || '');
  const target = String(handle || '').replace(/^@/, '').toLowerCase();
  if (!target) return false;
  const matches = [...body.matchAll(/(?:Unfollow|取消关注|取消關注|取消跟随|取消跟隨)\s+@([A-Za-z0-9_]{1,15})/gi)];
  return matches.some((match) => match[1].toLowerCase() === target);
}

function isExactUnfollowMenuItem(text, handle) {
  const label = String(text || '').trim();
  const target = String(handle || '').replace(/^@/, '').toLowerCase();
  const match = label.match(/^(?:Unfollow|取消关注|取消關注|取消跟随|取消跟隨)\s+@([A-Za-z0-9_]{1,15})\s*$/i);
  return Boolean(match && target && match[1].toLowerCase() === target);
}

function isVerifiedNotFollowingState(state) {
  return Boolean(state && state.stillUnfollow === false && state.nowFollow === true);
}

function isTargetProfileFollowingYou(scope) {
  const safeScope = scope || {};
  const targetHeaderText = [safeScope.userNameText, safeScope.profileHeaderText]
    .map((value) => String(value || ''))
    .join('\n');
  return /(?:^|\n)\s*(?:Follows you|关注了你|跟隨你)\s*(?:$|\n)/i.test(targetHeaderText);
}

function shouldSkipMutual(state) {
  const value = state || {};
  return Boolean(value.followsYou && !(value.allowMutual && value.explicitHandles));
}

module.exports = {
  UNFOLLOW_CONFIRM_CONTAINER_SELECTOR,
  isExactUnfollowControl,
  isExactFollowControl,
  isExactUnfollowConfirmation,
  isExactUnfollowMenuItem,
  isVerifiedNotFollowingState,
  isTargetProfileFollowingYou,
  shouldSkipMutual,
};
