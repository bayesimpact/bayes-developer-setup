interface Window {
  extractPPPP?: (name?: string, part?: string) => Promise<void>
  ppppName?: string
  ppppPart?: string
}

interface WorkflowyItem {
  ch?: readonly WorkflowyItem[]
  nm?: string
}

interface InitData {
  projectTreeData: {
    mainProjectTreeInfo: {
      rootProjectChildren: readonly WorkflowyItem[]
    }
  }
}

if (!window.extractPPPP) {
  window.extractPPPP = (name?: string, part?: string) => {

    const shareId = 'hfEXkyAJXu'

    const makeItemReport = ({ch, nm}: WorkflowyItem = {}, keepName = false): string =>
      (keepName ? `<li>${nm || ''}` : '') +
        (ch ? `<ul>${ch.map(c => makeItemReport(c, true)).join('\n')}</ul>` : '') +
        (keepName ? '</li>' : '')

    const makeWeekReport = (week: WorkflowyItem, name: string, part: string) => {
      const parts = week.ch.
        find(({nm}) => nm === 'PPPP')?.ch?.
        find(({nm}) => nm === name)?.ch?.
        find(({nm}) => nm === part)
      return `<h3>${week.nm || ''}</h3>${parts?.ch?.length ? makeItemReport(parts) : ''}`
    }

    const fetchData = async (name: string, part: string): Promise<string> => {
      window.ppppName = name
      window.ppppPart = part
      const initDataResponse = await fetch(
        `https://workflowy.com/get_initialization_data?share_id=${shareId}&client_version=21`)
      const initData: InitData = await initDataResponse.json()
      const weekly = initData.projectTreeData.mainProjectTreeInfo.rootProjectChildren[1].ch || []
      return weekly.
        filter(({nm}) => nm.startsWith('FR')).
        map(w => makeWeekReport(w, name, part)).reverse().join('\n\n')
    }

    const showReport = (report: string) => {
      open('').document.body.innerHTML = report
    }

    return fetchData(
      name || prompt("What's your name?", window.ppppName),
      part || prompt("What part of your PPPP do you want to check?", window.ppppPart || 'Progress'),
    ).then(showReport)
  }
}

window.extractPPPP()
