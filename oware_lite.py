#!/usr/bin/env python3
"""oware-lite: 极简 Oware（播棋）引擎，纯标准库。

规则（常见比赛规则简化版）：
- 2x6 棋盘，每坑开局 4 子，共 48 子。
- 南家（玩家 0）拥有 0-5 号坑，北家（玩家 1）拥有 6-11 号坑。
- 每回合从己方非空坑抓起全部种子，逆时针逐坑播一子；
  播种子数 >= 12 时跳过起点坑。
- 最后一子若落在对方一侧且该坑变为 2 或 3 子，则吃掉该坑，
  并向后连续吃掉对方一侧所有 2/3 子的坑（遇到己方一侧或
  非 2/3 子即停）。
- 大满贯保护：若一次能吃光对方全部种子，则本次不吃（放弃）。
- 断粮规则：对方一侧无子时，必须走能给对方送子的走法；
  若没有任何走法能送子，对局结束，轮走方拿走棋盘上所有剩余种子。
- 先拿到 25 子（>24）即胜；否则子多者胜，24-24 为和棋。
"""

import argparse
import random
import sys

PITS = 12
START_SEEDS = 4
WIN_SCORE = 25          # 拿到 25 子即胜（总共 48 子）
MAX_HALF_MOVES = 400    # 防无限循环上限


def new_board():
    """开局棋盘：每坑 4 子。"""
    return [START_SEEDS] * PITS


def side_pits(player):
    """玩家拥有的坑位。0=南(0-5)，1=北(6-11)。"""
    if player == 0:
        return range(0, 6)
    return range(6, 12)


def is_opponent_pit(pit, player):
    return (pit >= 6) if player == 0 else (pit < 6)


def side_total(board, player):
    return sum(board[p] for p in side_pits(player))


def sow(board, pit):
    """播种：返回 (新棋盘, 最后一子落点)。不改变原棋盘。"""
    seeds = board[pit]
    b = board[:]
    b[pit] = 0
    pos = pit
    for _ in range(seeds):
        pos = (pos + 1) % PITS
        if pos == pit:          # 播满一圈时跳过起点坑
            pos = (pos + 1) % PITS
        b[pos] += 1
    return b, pos


def _feeds_opponent(board, player, pit):
    """该走法是否会给对方一侧送去至少一子。"""
    seeds = board[pit]
    pos = pit
    for _ in range(seeds):
        pos = (pos + 1) % PITS
        if pos == pit:
            pos = (pos + 1) % PITS
        if is_opponent_pit(pos, player):
            return True
    return False


def legal_moves(board, player):
    """合法走法（含断粮喂子约束）。返回坑位索引列表。"""
    opp_empty = side_total(board, 1 - player) == 0
    moves = []
    for pit in side_pits(player):
        if board[pit] == 0:
            continue
        if opp_empty and not _feeds_opponent(board, player, pit):
            continue
        moves.append(pit)
    return moves


def do_capture(board, player, last):
    """吃子（原地修改 board）。返回吃到的子数。"""
    if not is_opponent_pit(last, player):
        return 0
    if board[last] not in (2, 3):
        return 0
    victims = []
    p = last
    while is_opponent_pit(p, player) and board[p] in (2, 3):
        victims.append(p)
        p = (p - 1) % PITS
    captured = sum(board[p] for p in victims)
    if captured == side_total(board, 1 - player):
        return 0            # 大满贯：会吃光对方则放弃本次吃子
    for p in victims:
        board[p] = 0
    return captured


def apply_move(board, scores, player, pit):
    """执行一步。非法走法抛 ValueError。返回 (新棋盘, 落点, 吃子数)。

    board 会被复制；scores 原地累加。
    """
    if pit not in side_pits(player):
        raise ValueError("只能走自己一侧的坑")
    if board[pit] == 0:
        raise ValueError("空坑不能走")
    if pit not in legal_moves(board, player):
        raise ValueError("对方断粮时必须走能送子的走法")
    b, last = sow(board, pit)
    captured = do_capture(b, player, last)
    scores[player] += captured
    return b, last, captured


def ai_choose(board, scores, player, moves, rng):
    """贪心 AI：优先吃子数，其次播子数，最后随机打破平局。"""
    best_pit = moves[0]
    best_key = None
    for pit in moves:
        b2 = board[:]
        s2 = scores[:]
        _, _, captured = apply_move(b2, s2, player, pit)
        key = (captured, board[pit], rng.random())
        if best_key is None or key > best_key:
            best_key = key
            best_pit = pit
    return best_pit


def play_game(rng, verbose=False):
    """AI 对 AI 一局。返回 (scores, winner, reason)。

    winner: 0/1/None(和棋)；reason: win/starve/empty/loop。
    """
    board = new_board()
    scores = [0, 0]
    player = 0
    half = 0
    while half < MAX_HALF_MOVES:
        moves = legal_moves(board, player)
        if not moves:
            # 无法喂子：轮走方拿走棋盘上所有剩余种子，对局结束
            scores[player] += sum(board)
            return scores, player, "starve"
        pit = ai_choose(board, scores, player, moves, rng)
        board, _, captured = apply_move(board, scores, player, pit)
        half += 1
        if verbose:
            print(f"  {'南' if player == 0 else '北'} 走坑 {pit}，吃 {captured} 子 "
                  f"（{scores[0]}:{scores[1]}）")
        if scores[player] >= WIN_SCORE:
            return scores, player, "win"
        if sum(board) == 0:
            return scores, player, "empty"
        player = 1 - player
    # 循环上限：双方各拿走自己一侧剩余种子
    for p in (0, 1):
        scores[p] += side_total(board, p)
    if scores[0] > scores[1]:
        return scores, 0, "loop"
    if scores[1] > scores[0]:
        return scores, 1, "loop"
    return scores, None, "loop"


def render(board, scores):
    top = " ".join(f"[{board[p]:2d}]" for p in range(11, 5, -1))
    bot = " ".join(f"[{board[p]:2d}]" for p in range(0, 6))
    nums = " ".join(f"  {i+1} " for i in range(6))
    return (f"      北 (AI)  得分 {scores[1]}\n"
            f"  {top}\n"
            f"  {bot}\n"
            f"  {nums}\n"
            f"      南 (你)  得分 {scores[0]}")


def play_interactive():
    if not sys.stdin.isatty():
        print("交互模式需要终端；无头演示请用 --auto", file=sys.stderr)
        sys.exit(2)
    rng = random.Random()
    board = new_board()
    scores = [0, 0]
    player = 0
    half = 0
    print("Oware 播棋：你是南家（下方），输入 1-6 选择己方坑位，q 退出。")
    while half < MAX_HALF_MOVES:
        print()
        print(render(board, scores))
        moves = legal_moves(board, player)
        if not moves:
            scores[player] += sum(board)
            name = "你" if player == 0 else "AI"
            print(f"\n对方断粮且无法喂子，{name}拿走剩余 {sum(board)} 子，对局结束。")
            break
        if player == 0:
            prompt = f"轮到你走（可选坑 {sorted(m + 1 for m in moves)}）："
            while True:
                try:
                    raw = input(prompt).strip().lower()
                except EOFError:
                    print("\n再见。")
                    return
                if raw in ("q", "quit", "exit"):
                    print("再见。")
                    return
                try:
                    pit = int(raw) - 1
                except ValueError:
                    print("请输入 1-6 的数字。")
                    continue
                if pit in moves:
                    break
                print("非法走法，请重选。")
        else:
            pit = ai_choose(board, scores, player, moves, rng)
            print(f"AI 走坑 {pit - 5}。")
        board, _, captured = apply_move(board, scores, player, pit)
        if captured:
            who = "你吃掉" if player == 0 else "AI 吃掉"
            print(f"{who} {captured} 子！")
        half += 1
        if scores[player] >= WIN_SCORE:
            break
        if sum(board) == 0:
            break
        player = 1 - player
    else:
        for p in (0, 1):
            scores[p] += side_total(board, p)
    print()
    print(render(board, [0, 0]))
    print(f"\n终局得分：你 {scores[0]} : {scores[1]} AI")
    if scores[0] > scores[1]:
        print("你赢了！")
    elif scores[1] > scores[0]:
        print("AI 赢了。")
    else:
        print("和棋。")


def play_auto(games, seed, verbose):
    rng = random.Random(seed)
    tally = {"south": 0, "north": 0, "draw": 0}
    for i in range(games):
        scores, winner, reason = play_game(rng, verbose=verbose)
        if winner == 0:
            tally["south"] += 1
            who = "南胜"
        elif winner == 1:
            tally["north"] += 1
            who = "北胜"
        else:
            tally["draw"] += 1
            who = "和棋"
        print(f"第 {i + 1}/{games} 局：{who}（{scores[0]}:{scores[1]}，{reason}）")
    print(f"总计：南胜 {tally['south']}，北胜 {tally['north']}，和棋 {tally['draw']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Oware 播棋（极简版）")
    ap.add_argument("--auto", action="store_true", help="AI 对 AI 自动演示")
    ap.add_argument("--games", type=int, default=10, help="自动演示局数")
    ap.add_argument("--seed", type=int, default=42, help="随机种子")
    ap.add_argument("--verbose", action="store_true", help="自动演示打印每步")
    args = ap.parse_args(argv)
    if args.auto:
        play_auto(args.games, args.seed, args.verbose)
    else:
        play_interactive()


if __name__ == "__main__":
    main()
